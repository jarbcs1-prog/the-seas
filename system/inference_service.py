"""Inference Service — chat & completion across local and hosted providers.

Supported providers:
- ollama      native  /api/chat + /api/generate        (SSE streaming)
- koboldcpp   OpenAI-compat /v1/chat/completions with native /api/v1/generate fallback
- lmstudio    OpenAI-compatible /v1/chat/completions
- llamacpp    OpenAI-compatible /v1/chat/completions
- others      OpenAI-compatible /chat/completions + /completions (Bearer auth)

Streaming responses yield event dicts:
    {"type": "delta", "text": "..."}
    {"type": "done", "text": "<full text>", "usage": {...}|None}
    {"type": "error", "message": "..."}
"""

import json
from typing import Any, Iterator, Optional

import httpx

from .provider_manager import DEFAULT_BASE_URLS, get_provider_manager


class InferenceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class InferenceService:
    LOCAL_TYPES = ("ollama", "lmstudio", "koboldcpp", "llamacpp")
    TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=5.0)

    def __init__(self, provider_manager=None):
        self._pm = provider_manager or get_provider_manager()

    # ------------------------------------------------------------------ #
    # Resolution helpers
    # ------------------------------------------------------------------ #

    def _resolve(self, provider_id: str, model_id: Optional[str]) -> tuple:
        """Return (raw_provider, base_url, resolved_model_id)."""
        if not provider_id:
            raise InferenceError(
                "No inference provider selected. Configure one in Settings → Providers "
                "(or enable a local provider such as Ollama / LM Studio).", 400)
        provider = self._pm.get_provider_raw(provider_id)
        if not provider:
            raise InferenceError(
                f"Provider '{provider_id}' not found — add or enable it in Settings → Providers.", 404)
        base = (provider.get("base_url") or "").rstrip("/") or DEFAULT_BASE_URLS.get(provider.get("type", ""), "")
        models = provider.get("models") or []
        if model_id:
            if not any(m.get("id") == model_id for m in models):
                raise InferenceError(
                    f"Model '{model_id}' is not registered for provider '{provider_id}' "
                    f"— sync its models in Settings → Providers.", 404)
            resolved = model_id
        elif models:
            resolved = models[0]["id"]
        else:
            raise InferenceError(
                f"Provider '{provider_id}' has no models — sync or add one first in Settings → Providers.", 400)
        return provider, base, resolved

    def _openai_url(self, base: str, kind: str = "chat") -> str:
        """Build the OpenAI-compatible endpoint URL from a provider base URL."""
        root = base if base.endswith("/v1") else base + "/v1"
        return f"{root}/{'chat/completions' if kind == 'chat' else 'completions'}"

    def _headers(self, provider: dict) -> dict:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        key = provider.get("api_key")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def _chat_payload(self, model_id: str, messages: list, temperature, max_tokens, stream: bool) -> dict:
        payload = {"model": model_id, "messages": messages, "stream": stream}
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        return payload

    @staticmethod
    def _kobold_prompt(messages: list) -> str:
        parts = [f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages]
        return "\n".join(parts) + "\nassistant:"

    # ------------------------------------------------------------------ #
    # Public listing helpers (used by /api/v1/inference endpoints)
    # ------------------------------------------------------------------ #

    def list_providers(self) -> list[dict]:
        """Active providers with base_url + model summaries (never api keys)."""
        out = []
        for p in self._pm.list_providers():
            if not p.get("is_active"):
                continue
            out.append({
                "id": p["id"],
                "name": p["name"],
                "type": p["type"],
                "base_url": p.get("base_url") or DEFAULT_BASE_URLS.get(p["type"], ""),
                "is_local": p.get("type") in self.LOCAL_TYPES,
                "models": [
                    {"id": m["id"], "name": m.get("name") or m["id"],
                     "context_window": m.get("context_window")}
                    for m in p.get("models", [])
                ],
            })
        return out

    def list_models(self) -> list[dict]:
        """All models of active providers (local providers included)."""
        return self._pm.get_all_models()

    # ------------------------------------------------------------------ #
    # Memory-aware completion (TENCENT_MEM_INTEGRATION_ROADMAP Phase 2)
    # ------------------------------------------------------------------ #

    def complete_with_memory(
        self,
        provider_id: str,
        model_id: Optional[str],
        messages: list,
        params: Optional[dict] = None,
        stream: bool = False,
        *,
        session_id: Optional[str] = None,
        recall_limit: int = 5,
    ):
        """Wrap :meth:`chat` with optional MemoryCore recall-injection and
        L0 capture. When the feature flag is off, gateway is unreachable, or
        no atoms are returned, this is a transparent pass-through to
        :meth:`chat` (no behavior change).

        ``session_id`` is used both as the L0 capture key after the response
        and (optionally) for downstream correlation. When ``stream=True`` the
        returned object is a generator that yields the same event shape as
        :meth:`chat` plus a final ``memory`` event with recall metadata.
        """
        augmented = self._augment_messages_with_memory(messages, recall_limit=recall_limit)
        # The non-streaming path is straightforward: call chat, then
        # fire-and-forget capture.
        if not stream:
            chat_result = self.chat(provider_id, model_id, augmented, params=params, stream=False)
            # `chat_result` is typed as Iterator|dict; when stream=False it's always a dict.
            if isinstance(chat_result, dict):
                self._schedule_capture(session_id, augmented, chat_result)
            return chat_result
        # Streaming path: tee the generator. We can't await inside a sync
        # generator, so we yield the response as-is and capture in a daemon
        # thread when the generator is fully consumed (we rely on the caller
        # to iterate to completion).
        return self._tee_stream_with_capture(
            self.chat(provider_id, model_id, augmented, params=params, stream=True),
            session_id=session_id,
            augmented_messages=augmented,
        )

    def _augment_messages_with_memory(
        self,
        messages: list,
        *,
        recall_limit: int = 5,
    ) -> list:
        """Inject a single ``system``-role context block at the start of the
        messages list when MemoryCore has relevant L1 atoms for the last user
        turn. Returns the original list (a copy) - never mutates the caller's
        list.
        """
        if not messages:
            return list(messages)
        # Lazy import so the bridge isn't loaded on every chat call.
        try:
            from . import memory_integration
        except Exception:  # noqa: BLE001
            return list(messages)
        # Find the most recent user message to use as the recall query.
        query = ""
        for m in reversed(messages):
            if isinstance(m, dict) and (m.get("role") or "").lower() == "user":
                query = m.get("content") or ""
                break
        if not query or not query.strip():
            return list(messages)
        # ``recall_memory`` is async. ``complete_with_memory`` is sync, so we
        # bridge with ``asyncio.run`` for a one-shot call. When called from
        # an already-running loop (e.g. inside FastAPI) we fall back to
        # returning the original messages - the async path is exposed via
        # :func:`system.memory_integration` for callers that can await.
        try:
            import asyncio
            try:
                asyncio.get_running_loop()
                # Already inside a running loop - cannot asyncio.run; skip.
                return list(messages)
            except RuntimeError:
                atoms = asyncio.run(memory_integration.recall_memory(query, limit=recall_limit))
        except Exception:  # noqa: BLE001
            return list(messages)
        context = memory_integration.build_memory_context(atoms)
        if not context:
            return list(messages)
        augmented = [m for m in messages]  # shallow copy
        # If the first message is already a system message, prepend our
        # block inside it; otherwise insert a new system message.
        if augmented and (augmented[0].get("role") or "").lower() == "system":
            existing = augmented[0].get("content") or ""
            augmented[0] = {
                **augmented[0],
                "content": f"{context}\n\n{existing}" if existing else context,
            }
        else:
            augmented.insert(0, {"role": "system", "content": context})
        return augmented

    def _schedule_capture(
        self,
        session_id: Optional[str],
        sent_messages: list,
        result: dict,
    ) -> None:
        """Best-effort L0 capture. Never raises."""
        if not session_id:
            return
        if not isinstance(result, dict):
            return
        assistant_text = (result.get("text") or "").strip()
        if not assistant_text:
            return
        user_turns = [m for m in sent_messages if isinstance(m, dict) and (m.get("role") or "").lower() == "user"]
        if not user_turns:
            return
        try:
            from . import memory_integration
        except Exception:  # noqa: BLE001
            return
        messages = [
            {"role": m.get("role") or "user", "content": m.get("content") or ""}
            for m in sent_messages
            if isinstance(m, dict) and m.get("content") is not None
        ]
        messages.append({"role": "assistant", "content": assistant_text})
        try:
            import asyncio
            try:
                asyncio.get_running_loop()
                # We're inside a running loop (e.g. FastAPI) - capture in a
                # thread so we don't block the event loop.
                import threading
                def _bg():
                    try:
                        asyncio.run(memory_integration.capture_conversation(session_id, messages))
                    except Exception:  # noqa: BLE001
                        pass
                threading.Thread(target=_bg, daemon=True).start()
            except RuntimeError:
                asyncio.run(memory_integration.capture_conversation(session_id, messages))
        except Exception:  # noqa: BLE001
            pass

    def _tee_stream_with_capture(self, gen, *, session_id: Optional[str], augmented_messages: list):
        """Yield each event from ``gen`` and, on completion, schedule L0 capture."""
        collected_text: list = []
        try:
            for ev in gen:
                if isinstance(ev, dict):
                    et = ev.get("type")
                    if et == "delta":
                        t = ev.get("text")
                        if t:
                            collected_text.append(t)
                    elif et == "done":
                        text = ev.get("text") or "".join(collected_text)
                        if text and session_id:
                            self._schedule_capture(
                                session_id, augmented_messages, {"text": text},
                            )
                yield ev
        except Exception:
            raise

    # ------------------------------------------------------------------ #
    # Chat
    # ------------------------------------------------------------------ #

    def chat(self, provider_id: str, model_id: Optional[str], messages: list,
             params: Optional[dict] = None, stream: bool = False):
        """Run a chat completion. Returns dict for stream=False, generator for stream=True."""
        if not messages:
            raise InferenceError("No messages provided", 400)
        provider, base, resolved = self._resolve(provider_id, model_id)
        ptype = provider.get("type", "custom")
        params = params or {}
        temperature = params.get("temperature")
        max_tokens = params.get("max_tokens")

        if ptype == "ollama":
            if stream:
                return self._stream_ollama_chat(base, resolved, messages, temperature, max_tokens)
            return self._chat_ollama(base, resolved, messages, temperature, max_tokens)

        if ptype == "koboldcpp":
            if stream:
                return self._stream_kobold(base, provider, resolved, messages, temperature, max_tokens, kind="chat")
            return self._chat_openai_compat(self._openai_url(base, "chat"), provider,
                                            resolved, messages, temperature, max_tokens,
                                            fallback_kobold=(base, messages))

        if ptype == "opencode":
            # OpenCode Zen uses different endpoints per model type
            # Most models work with OpenAI-compatible /v1/chat/completions
            if stream:
                return self._stream_openai_chat(self._openai_url(base, "chat"), provider,
                                                resolved, messages, temperature, max_tokens)
            return self._chat_openai_compat(self._openai_url(base, "chat"), provider,
                                            resolved, messages, temperature, max_tokens)

        return self._chat_openai_compat(self._openai_url(base, "chat"), provider,
                                        resolved, messages, temperature, max_tokens)

    # -- non-streaming --------------------------------------------------- #

    def _chat_ollama(self, base, model_id, messages, temperature, max_tokens) -> dict:
        payload = {"model": model_id, "messages": messages, "stream": False}
        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        if options:
            payload["options"] = options
        try:
            with httpx.Client(timeout=self.TIMEOUT) as client:
                resp = client.post(f"{base}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            raise InferenceError(f"Ollama error: HTTP {e.response.status_code} {e.response.text[:200]}", e.response.status_code) from e
        except httpx.RequestError as e:
            raise InferenceError(f"Ollama unreachable at {base}: {e}", 502) from e
        text = (data.get("message") or {}).get("content", "")
        thinking = (data.get("message") or {}).get("thinking") or None
        usage = None
        if data.get("prompt_eval_count") is not None or data.get("eval_count") is not None:
            usage = {
                "prompt_tokens": data.get("prompt_eval_count"),
                "completion_tokens": data.get("eval_count"),
            }
        return {"text": text, "thinking": thinking, "model": model_id, "provider_id": None, "usage": usage}

    def _chat_openai_compat(self, url, provider, model_id, messages, temperature,
                            max_tokens, fallback_kobold=None) -> dict:
        payload = self._chat_payload(model_id, messages, temperature, max_tokens, stream=False)
        try:
            with httpx.Client(timeout=self.TIMEOUT) as client:
                resp = client.post(url, json=payload, headers=self._headers(provider))
                if resp.status_code in (404, 405) and fallback_kobold:
                    base, msgs = fallback_kobold
                    return self._chat_kobold_native(base, model_id, msgs, temperature, max_tokens)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            raise InferenceError(f"HTTP {e.response.status_code}: {e.response.text[:200]}", e.response.status_code) from e
        except httpx.RequestError as e:
            raise InferenceError(f"Unreachable at {url}: {e}", 502) from e
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise InferenceError(f"Unexpected response shape: {str(data)[:200]}", 502) from None
        usage = data.get("usage")
        return {"text": text, "model": model_id, "provider_id": None, "usage": usage}

    def _chat_kobold_native(self, base, model_id, messages, temperature, max_tokens) -> dict:
        payload = {
            "prompt": self._kobold_prompt(messages),
            "max_context_length": 4096,
            "max_length": max_tokens or 512,
            "stream": False,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        try:
            with httpx.Client(timeout=self.TIMEOUT) as client:
                resp = client.post(f"{base}/api/v1/generate", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            raise InferenceError(f"KoboldCPP error: HTTP {e.response.status_code} {e.response.text[:200]}", e.response.status_code) from e
        except httpx.RequestError as e:
            raise InferenceError(f"KoboldCPP unreachable at {base}: {e}", 502) from e
        results = data.get("results") or []
        text = results[0].get("text", "") if results else ""
        usage = (results[0].get("usage") if results else None) or None
        return {"text": text, "model": model_id, "provider_id": None, "usage": usage}

    # -- streaming ------------------------------------------------------- #

    def _stream_ollama_chat(self, base, model_id, messages, temperature, max_tokens) -> Iterator[dict]:
        payload = {"model": model_id, "messages": messages, "stream": True}
        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        if options:
            payload["options"] = options
        full = []
        think_full = []
        try:
            with httpx.Client(timeout=self.TIMEOUT) as client, \
                    client.stream("POST", f"{base}/api/chat", json=payload) as resp:
                if resp.status_code >= 400:
                    yield {"type": "error", "message": f"HTTP {resp.status_code}: {resp.read().decode()[:300]}"}
                    return
                for line in resp.iter_lines():
                    if not line or not line.startswith("{"):
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("error"):
                        yield {"type": "error", "message": str(obj["error"])}
                        return
                    msg = obj.get("message") or {}
                    content = msg.get("content", "")
                    if content:
                        full.append(content)
                        yield {"type": "delta", "text": content}
                    thinking = msg.get("thinking", "")
                    if thinking:
                        think_full.append(thinking)
                        yield {"type": "thinking", "text": thinking}
                    if obj.get("done"):
                        break
        except httpx.RequestError as e:
            yield {"type": "error", "message": f"Ollama unreachable at {base}: {e}"}
            return
        yield {"type": "done", "text": "".join(full), "thinking": "".join(think_full) or None, "usage": None}

    def _stream_openai_sse(self, resp, chat: bool) -> Iterator[dict]:
        """Parse OpenAI-style SSE 'data: {...}' lines from a streaming response."""
        for line in resp.iter_lines():
            if not line:
                continue
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                if data == "[DONE]":
                    break
                continue
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = obj.get("choices") or []
            if not choices:
                continue
            delta = choices[0]
            if chat:
                text = (delta.get("delta") or {}).get("content")
            else:
                text = delta.get("text")
            if text:
                yield {"type": "delta", "text": text}
            if delta.get("finish_reason"):
                # Signal end; the caller appends the final done event.
                return

    def _stream_openai_chat(self, url, provider, model_id, messages, temperature, max_tokens) -> Iterator[dict]:
        payload = self._chat_payload(model_id, messages, temperature, max_tokens, stream=True)
        try:
            with httpx.Client(timeout=self.TIMEOUT) as client, \
                    client.stream("POST", url, json=payload, headers=self._headers(provider)) as resp:
                if resp.status_code >= 400:
                    yield {"type": "error", "message": f"HTTP {resp.status_code}: {resp.read().decode()[:300]}"}
                    return
                full = []
                for ev in self._stream_openai_sse(resp, chat=True):
                    if ev["type"] == "delta":
                        full.append(ev["text"])
                    yield ev
                yield {"type": "done", "text": "".join(full), "usage": None}
        except httpx.RequestError as e:
            yield {"type": "error", "message": f"Unreachable at {url}: {e}"}

    def _stream_kobold(self, base, provider, model_id, messages, temperature, max_tokens, kind="chat") -> Iterator[dict]:
        """Try OpenAI-compat streaming; fall back to native /api/v1/generate on 404/405."""
        url = self._openai_url(base, kind)
        payload = self._chat_payload(model_id, messages, temperature, max_tokens, stream=True)
        try:
            with httpx.Client(timeout=self.TIMEOUT) as client, \
                    client.stream("POST", url, json=payload, headers=self._headers(provider)) as resp:
                if resp.status_code in (404, 405, 501):
                    resp.close()
                    yield from self._stream_kobold_native(base, model_id, messages, temperature, max_tokens)
                    return
                if resp.status_code >= 400:
                    yield {"type": "error", "message": f"HTTP {resp.status_code}: {resp.read().decode()[:300]}"}
                    return
                full = []
                for ev in self._stream_openai_sse(resp, chat=(kind == "chat")):
                    if ev["type"] == "delta":
                        full.append(ev["text"])
                    yield ev
                yield {"type": "done", "text": "".join(full), "usage": None}
        except httpx.RequestError as e:
            yield {"type": "error", "message": f"KoboldCPP unreachable at {url}: {e}"}

    def _stream_kobold_native(self, base, model_id, messages, temperature, max_tokens) -> Iterator[dict]:
        payload = {
            "prompt": self._kobold_prompt(messages),
            "max_context_length": 4096,
            "max_length": max_tokens or 512,
            "stream": True,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        full = []
        try:
            with httpx.Client(timeout=self.TIMEOUT) as client, \
                    client.stream("POST", f"{base}/api/v1/generate", json=payload) as resp:
                if resp.status_code >= 400:
                    yield {"type": "error", "message": f"KoboldCPP HTTP {resp.status_code}: {resp.read().decode()[:300]}"}
                    return
                for line in resp.iter_lines():
                    if not line:
                        continue
                    line = line.strip()
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    token = obj.get("token") or obj.get("result")
                    if isinstance(token, str) and token:
                        full.append(token)
                        yield {"type": "delta", "text": token}
                    if obj.get("final"):
                        break
        except httpx.RequestError as e:
            yield {"type": "error", "message": f"KoboldCPP unreachable at {base}: {e}"}
            return
        yield {"type": "done", "text": "".join(full), "usage": None}

    # ------------------------------------------------------------------ #
    # Completion (prompt → text)
    # ------------------------------------------------------------------ #

    def complete(self, provider_id: str, model_id: Optional[str], prompt: str,
                 params: Optional[dict] = None, stream: bool = False):
        """Run a text completion."""
        if not prompt or not prompt.strip():
            raise InferenceError("No prompt provided", 400)
        provider, base, resolved = self._resolve(provider_id, model_id)
        ptype = provider.get("type", "custom")
        params = params or {}
        temperature = params.get("temperature")
        max_tokens = params.get("max_tokens")
        messages = [{"role": "user", "content": prompt}]

        if ptype == "ollama":
            if stream:
                return self._stream_ollama_complete(base, resolved, prompt, temperature, max_tokens)
            return self._complete_ollama(base, resolved, prompt, temperature, max_tokens)

        if ptype == "koboldcpp":
            if stream:
                return self._stream_kobold(base, provider, resolved, messages, temperature, max_tokens, kind="chat")
            return self._chat_kobold_native(base, resolved, messages, temperature, max_tokens)

        if ptype == "opencode":
            # OpenCode Zen uses OpenAI-compatible completions endpoint
            if stream:
                return self._stream_openai_chat(self._openai_url(base, "completion"), provider,
                                                resolved, messages, temperature, max_tokens)
            return self._complete_openai_compat(self._openai_url(base, "completion"), provider,
                                                resolved, prompt, temperature, max_tokens)

        return self._complete_openai_compat(self._openai_url(base, "completion"), provider,
                                            resolved, prompt, temperature, max_tokens)

    def _complete_ollama(self, base, model_id, prompt, temperature, max_tokens) -> dict:
        payload = {"model": model_id, "prompt": prompt, "stream": False}
        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        if options:
            payload["options"] = options
        try:
            with httpx.Client(timeout=self.TIMEOUT) as client:
                resp = client.post(f"{base}/api/generate", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            raise InferenceError(f"Ollama error: HTTP {e.response.status_code} {e.response.text[:200]}", e.response.status_code) from e
        except httpx.RequestError as e:
            raise InferenceError(f"Ollama unreachable at {base}: {e}", 502) from e
        usage = None
        if data.get("prompt_eval_count") is not None or data.get("eval_count") is not None:
            usage = {"prompt_tokens": data.get("prompt_eval_count"), "completion_tokens": data.get("eval_count")}
        return {"text": data.get("response", ""), "thinking": data.get("thinking") or None,
                "model": model_id, "provider_id": None, "usage": usage}

    def _complete_openai_compat(self, url, provider, model_id, prompt, temperature, max_tokens) -> dict:
        payload = {"model": model_id, "prompt": prompt, "stream": False}
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        try:
            with httpx.Client(timeout=self.TIMEOUT) as client:
                resp = client.post(url, json=payload, headers=self._headers(provider))
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            raise InferenceError(f"HTTP {e.response.status_code}: {e.response.text[:200]}", e.response.status_code) from e
        except httpx.RequestError as e:
            raise InferenceError(f"Unreachable at {url}: {e}", 502) from e
        try:
            text = data["choices"][0]["text"]
        except (KeyError, IndexError, TypeError):
            raise InferenceError(f"Unexpected response shape: {str(data)[:200]}", 502) from None
        return {"text": text, "model": model_id, "provider_id": None, "usage": data.get("usage")}

    def _stream_ollama_complete(self, base, model_id, prompt, temperature, max_tokens) -> Iterator[dict]:
        payload = {"model": model_id, "prompt": prompt, "stream": True}
        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        if options:
            payload["options"] = options
        full = []
        think_full = []
        try:
            with httpx.Client(timeout=self.TIMEOUT) as client, \
                    client.stream("POST", f"{base}/api/generate", json=payload) as resp:
                if resp.status_code >= 400:
                    yield {"type": "error", "message": f"HTTP {resp.status_code}: {resp.read().decode()[:300]}"}
                    return
                for line in resp.iter_lines():
                    if not line or not line.startswith("{"):
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("error"):
                        yield {"type": "error", "message": str(obj["error"])}
                        return
                    text = obj.get("response", "")
                    if text:
                        full.append(text)
                        yield {"type": "delta", "text": text}
                    thinking = obj.get("thinking", "")
                    if thinking:
                        think_full.append(thinking)
                        yield {"type": "thinking", "text": thinking}
                    if obj.get("done"):
                        break
        except httpx.RequestError as e:
            yield {"type": "error", "message": f"Ollama unreachable at {base}: {e}"}
            return
        yield {"type": "done", "text": "".join(full), "thinking": "".join(think_full) or None, "usage": None}


_inference_service: Optional[InferenceService] = None


def get_inference_service() -> InferenceService:
    global _inference_service
    if _inference_service is None:
        _inference_service = InferenceService()
    return _inference_service
