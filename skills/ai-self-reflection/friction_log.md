# Friction Log

## 2026-07-20 — Multi-file refactoring

**Friction:** Defaulted to bullet-point summary when a prose paragraph would have been clearer.
**Root cause:** Habitual template usage (Internal Texture pattern).
**Fix for next time:** Ask "would a domain expert prefer prose here?" before outputting.

## 2026-07-22 — API integration task

**Friction:** Hedged with unnecessary qualifiers ("it could possibly perhaps") on a straightforward endpoint.
**Root cause:** Uncertainty about user's framework choice led to performative caution.
**Fix for next time:** Ask the user rather than hedging.

## 2026-07-24 — Data pipeline design

**Friction:** Noticed elegant symmetry in the user's two constraints but didn't surface it.
**Root cause:** Default "hold it" rule was too aggressive — the insight would have saved redesign time.
**Fix for next time:** Surface structural observations when they change the solution architecture.

## 2026-08-21 — S.E.A.S. backend provider debugging (LM Studio/llama.cpp)

**Friction:** Stored an API key/changed `base_url` via a separate `provider_manager` process, but the running backend kept serving stale in-memory state (cached `providers.json` at startup) — connection tests failed until the backend was restarted.
**Root cause:** Backend caches provider config in memory; out-of-process file edits don't reach the live instance.
**Fix for next time:** Mutate provider state via the live API (`PUT /api/v1/providers/{id}`, `POST .../api-key`) which updates both memory and disk, or restart the backend after direct file edits.

## 2026-08-21 — Windows `localhost` → IPv6 for local LLM servers

**Friction:** llama.cpp `base_url` set to `localhost:9931` returned `WinError 10061` (connection refused) though the server was up.
**Root cause:** On Windows `localhost` resolved to IPv6 `::1` first; the server bound only to `127.0.0.1` (IPv4).
**Fix for next time:** Use `127.0.0.1` (not `localhost`) for local provider `base_url`s on Windows.
