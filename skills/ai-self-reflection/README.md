# ai-self-reflection

Operational self-reflection protocol for AI agents. Detects friction spikes, maps introspective metaphors to concrete mechanics and provides a lightweight workflow for improving output quality.

## When to use

Load this skill when:
- A completed task felt mechanically "off"
- User feedback seems misaligned with your intended output
- You catch yourself using templated language
- A prompt is clearly out-of-distribution
- The user asks for meta-cognitive analysis

Do NOT load for simple factual questions or every interaction — reflection has overhead.

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | Full protocol: concepts, triggers, reflection workflow, surfacing rules, anti-patterns, conflict resolution |
| `original_reflection.md` | The introspective narrative that inspired the skill |
| `model_response.md` | Technical translation of the narrative's metaphors into AI-relevant terms |
| `friction_log.md` | Persistent log for cross-session friction pattern recognition |

## Quick start

1. Trigger conditions fire (see SKILL.md § Trigger Conditions)
2. Run pre-flight checklist before responding
3. Run post-hoc review after complex tasks
4. Log friction spikes to `friction_log.md`
5. Before complex tasks, scan recent log entries for recurring patterns
