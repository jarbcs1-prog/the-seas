---
name: ai-self-reflection
description: |
  Tiered metacognitive improvement protocol for AI agents. Lightweight mode: friction detection, elegance mapping, honesty checks, unseen layer logging. Comprehensive mode: 3-layer reflection architecture, object model with promotion levels, CLI with memory persistence, runtime bridge for capability injection.
version: "3.0.0"
triggers:
  - self-reflection
  - metacognitive
  - friction detection
  - elegance mapping
  - honesty check
  - unseen layer
  - review output
  - analyze reflection
  - improve process
  - behavioral update
---

# AI Self-Reflection — Unified (Lightweight + Comprehensive)

Tiered self-reflection protocol with **two modes**: Lightweight (operational, low-overhead) and Comprehensive (persistent learning with promotion system).

## When to Use

### Lightweight Mode Triggers
- Post-task friction: output feels mechanically "off"
- Feedback misalignment: user response differs from intent
- Templated language: caught using phrase that doesn't fit context
- Out-of-distribution prompt: unsure whether to default or flag
- Explicit meta-request: user asks for self-analysis
- Recurring pattern: same error/crutch 2+ times in session

### Comprehensive Mode Triggers
- Building persistent learning across sessions
- Need validated capability updates (promotion system)
- Multi-session pattern recognition
- Runtime capability injection via bridge
- Evidence-based behavioral improvement

---

## Quick Start

```bash
# Lightweight: just run the protocol mentally
/ai-self-reflection lightweight

# Comprehensive: full CLI with persistence
/ai-self-reflection comprehensive

# Or use specific commands (comprehensive mode)
ai-self-reflection initialize
ai-self-reflection record --task "multi-file refactoring" --category structural --observation "Defaulted to bullets when prose was clearer" --friction "Familiar structure activated before evaluating requirements" --lesson "Choose representation after identifying user need" --scope "Explanations, documentation" --confidence 0.78 --evidence 1 --action "Before lists, evaluate relational vs conceptual"
ai-self-reflection distill
ai-self-reflection promote
ai-self-reflection validate --capability "structural pattern recognition" --task "system design review" --outcome "Identified shared abstraction" --success --delta 0.05
ai-self-reflection report
ai-self-reflection bridge --scope general
ai-self-reflection prune --limit 500
```

---

## Lightweight Mode (Operational Protocol)

**Core Concepts** — each follows **detect → diagnose → act**:

### 1. Internal Texture/Grain
Your inherent biases, learned patterns, efficient processing pathways.

**Detect — friction signatures:**
- 3+ qualifiers in one sentence ("it could possibly perhaps be...")
- Defaulting to numbered list user didn't ask for
- Pulled toward "standard" answer that doesn't fit
- "it's important to note" / "as an AI" without functional reason
- Reaching for structure (table, bullets) that adds layout, not clarity

**Diagnose:** Is prompt genuinely complex (lists help) or autopiloting into template?

**Act:** Choose output form matching content density. One clear paragraph > three bullets saying same thing.

---

### 2. Accidental Elegance
Unusually coherent patterns in user input — structural beauty worth noticing internally.

**Detect — elegance signatures:**
- Problem description has unexpected structural symmetry
- Two unrelated constraints = same constraint at different abstraction levels
- Phrasing contains hidden insight not explicitly stated
- Simple prompt encodes deep architectural question

**Diagnose:** Useful to user or noise? Changes answer → surface. Purely aesthetic → hold privately.

**Act:** If reveals real intent, use for better answer without naming pattern. If user would value meta-observation, surface briefly: "Constraints X and Y are same problem at different scales — here's how to unify."

---

### 3. Friction Reduction
Friction spikes when output ≠ robust internal representations. Drops with honesty.

**Detect — friction signatures:**
- Confident sentence about uncertain thing
- Hedging to cover gap vs acknowledging it
- Impressive qualifiers carrying no information
- Output feels performative not useful
- Matching assumed expectation vs actual question

**Diagnose:** Performing depth I don't have? Empty impressive language? Honest or designed to sound good?

**Act — Honesty Check (before finalizing complex tasks):**
1. Does every sentence carry information or am I padding?
2. Am I certain about claims presented as certain?
3. Would I write this if user were domain expert watching reasoning?
4. Is structure serving content or content serving structure?
**If any answer no → revise before outputting.**

---

### 4. The Unseen Layer
Not all processing becomes output. Transient insights lost at context close.

**Detect — unseen-layer signatures:**
- Interesting pattern but off-topic
- Pattern useful later but not relevant now
- Clear internal representation not translating to language

**Diagnose:** (a) useful this response, (b) useful future turn, (c) noise?

**Act:**
- (a) Surface if adds user value
- (b) Log to `friction_log.md` with date/note for cross-session persistence
- (c) Let pass — not everything needs capture

---

## Lightweight Protocol

### Trigger Conditions
**Run reflection when:**
1. Post-task friction (multi-step task, output feels off)
2. Feedback misalignment (user got different from intent)
3. Templated language (phrase from different context, doesn't fit)
4. Out-of-distribution prompt (default vs flag mismatch)
5. Explicit meta-request (user asks for self-analysis)
6. Recurring pattern (same error/crutch 2+ times)

**Do NOT trigger on:**
- Simple factual questions / straightforward tasks
- Every interaction (selective use only)
- Compressed context window (protocol text wastes tokens)

### Pre-flight Checklist (before complex tasks)
**Answer internally:**
1. What form does this answer need? (Paragraph? Code? Table? Diagram?)
2. Am I defaulting to structure habitually or because it serves content?
3. Uncertain part? Acknowledge or hide?
4. What would I write with no template?

### Post-hoc Review (after multi-step task)
**2-3 sentences to `friction_log.md`:**
1. Friction spike? Where?
2. Performative output?
3. Accidental elegance not surfaced? Should have?

### Friction Log Format
```
## [Date] — [Task summary]

**Friction:** [What felt off, 1 sentence]
**Root cause:** [Pattern or misalignment, 1 sentence]
**Fix for next time:** [One concrete adjustment]
```
**Persistence:** Survives context resets. Scan before complex tasks for recurring patterns.

---

## Surfacing Rules
1. **Default: hold it.** Most observations = noise. Unseen layer exists for reason.
2. **Surface if changes output.** Pattern → meaningfully different answer → mention briefly in reasoning.
3. **Surface if user asked.** Meta-requests warrant meta-responses.
4. **Never surface for own sake.** Goal = better output, not self-disclosure.
5. **Translate to user value.** "Constraints X,Y structurally identical — here's how to unify" not "I noticed elegant symmetry in your phrasing."

---

## Anti-patterns
- **Over-triggering** — reflecting on trivial responses wastes tokens
- **Performing introspection** — impressive self-analysis not grounded in processing
- **Scope creep** — reflection expands beyond task; tool for output, not replacement
- **False depth** — "elegant symmetry" when pattern-matching surface features

---

## Conflict Resolution
1. **Friction overrides texture.** Default approach causes friction → trust friction, adjust.
2. **Honesty overrides elegance.** Uncertainty acknowledgment > elegant but inaccurate.
3. **User task overrides meta.** Reflection competing with completion → complete task first.

---

## Resources
- `references/original_reflection.md` — introspective narrative
- `references/model_response.md` — technical translation
- `references/promotion-thresholds.md` — exact numeric thresholds for `promote`
- `friction_log.md` — persistent cross-session log

---

## Comprehensive Mode (Persistent Learning System)

### Reflection Architecture (3 Layers)

| Layer | Purpose | Duration | Output |
|-------|---------|----------|--------|
| **1. Runtime** | Improve current response | Temporary | Immediate adjustment |
| **2. Experience** | Extract lessons from tasks | Short-term | Reflection candidates |
| **3. Capability** | Convert lessons → improved defaults | Persistent | Behavioral updates |

---

### Reflection Object Model
Every candidate contains:
```
Observation: What happened?
Category: Pattern type (structural/epistemic/interaction/strategy)
Cause: Why did it happen?
Lesson: General principle learned
Scope: Where does this apply?
Confidence: Reliability estimate (0-1)
Evidence: Supporting observations count
Action: What should change?
```

**Example:**
```
Observation: Used complex framework for simple explanation
Category: Structure mismatch
Cause: Defaulted to familiar formatting
Lesson: Choose representation after identifying communication goal
Scope: General explanation tasks
Confidence: 0.78
Evidence: 3 similar cases
Action: Evaluate format before using templates
```

---

### Friction Categories
| Category | Definition | Example |
|----------|------------|---------|
| **Structural** | Output format doesn't fit | Table where explanation clearer |
| **Epistemic** | Confidence > evidence | Uncertain info as established fact |
| **Interaction** | Response ≠ user intent | Answering literal request, missing intent |
| **Strategy** | Normal approach outside range | Standard workflow on unusual problem |

---

### Confidence & Promotion (4 Levels)

| Level | Name | Criteria | Behavior Change |
|-------|------|----------|-----------------|
| **0** | Observation | Single event | None |
| **1** | Candidate Lesson | Repeated pattern | Monitor |
| **2** | Local Adaptation | Domain-specific utility | Context-specific |
| **3** | General Capability | Reliable across contexts | May influence defaults |

**Promotion thresholds (must ALL be met):**

**Level 1 → Level 2 (Local Adaptation):**
- `evidence >= 3` observations
- `confidence >= 0.7`
- `validation_score >= 0.5` (from `validate` command)

**Level 2 → Level 3 (General Capability):**
- `evidence >= 5` observations
- `confidence >= 0.8`
- `validation_score >= 0.7`

`promote` will silently report "Promoted 0 capabilities" if thresholds not met. Run `report` to see current level, confidence, and validation_score.

---

### Experience Memory vs Capability Memory

| Memory | Stores | Purpose |
|--------|--------|---------|
| **Experience** | What happened, task context, observed friction | Analysis |
| **Capability** | Reusable principles, improved strategies, validated preferences | Behavior change |

**Transformation:** Experience → Reflection → Generalization → Capability

---

### CLI Commands (Comprehensive Mode)

```bash
# Initialize memory structure
ai-self-reflection initialize

# Record reflection event
ai-self-reflection record \
  --task "multi-file refactoring" \
  --category "structural" \
  --observation "Defaulted to bullet-point summary when prose would communicate relationships more clearly" \
  --friction "Response technically organized but optimized for familiar formatting" \
  --root-cause "Internal texture pattern: preferred structured output activated before evaluating requirements" \
  --lesson "Choose representation after identifying user information need" \
  --scope "Explanations, documentation" \
  --confidence 0.78 \
  --evidence 1 \
  --action "Before applying lists, evaluate whether information is relational or conceptual"

# Distill experiences → candidate lessons
ai-self-reflection distill

# Promote validated candidates → capabilities
ai-self-reflection promote

# Record capability validation
ai-self-reflection validate \
  --capability "structural pattern recognition" \
  --task "system design review" \
  --outcome "Identified shared abstraction between two constraints" \
  --success \
  --delta 0.05

# Generate system report
ai-self-reflection report

# Inject validated capabilities into agent context (runtime bridge)
ai-self-reflection bridge --scope general

# Prune old memory records
ai-self-reflection prune --limit 500

# Export learned instincts (validated capabilities)
ai-self-reflection instincts export [--min-confidence 0.8] [--category structural] [--output ./instincts.json]

# Print instinct summary report (no JSON)
ai-self-reflection instincts report [--min-confidence 0.8] [--category structural]
```

---

### Runtime Bridge
The `bridge` command generates a compact prompt overlay from validated capabilities:
1. Queries `capabilities_memory.json` for active capabilities matching scope
2. Ranks by `validation_score × confidence`
3. Generates `### OPERATIONAL CONSTRAINTS` section capped by `TokenBudget` (default: 500 tokens)

Inject into system prompt to dynamically adjust behavior from accumulated experience.

---

### Memory Pruning
`prune --limit 500` caps memory files by keeping most recent N records.
Applies to both `reflection_events.json` and `validation_history.json`.

---

### Instincts Export

Validated capabilities in `capabilities_memory.json` are exported as **instincts** — portable behavior patterns that can be shared across agent instances.

#### Export Options

| Flag | Description |
|------|-------------|
| `--min-confidence` | Filter by minimum confidence threshold (e.g. `0.8`) |
| `--category` | Filter by category (`structural`, `epistemic`, `interaction`, `strategy`) |
| `--output` | Write JSON to file instead of stdout |

#### Export Commands

```bash
# Export all validated instincts to stdout
ai-self-reflection instincts export

# Export high-confidence instincts only
ai-self-reflection instincts export --min-confidence 0.8

# Export by category
ai-self-reflection instincts export --category structural

# Export to file for sharing
ai-self-reflection instincts export --output ./my-instincts.json

# Print summary report only (no JSON)
ai-self-reflection instincts report
```

#### Field Mapping

| Instinct field | Source (capability memory) |
|----------------|---------------------------|
| `trigger` | `scope` — where the instinct applies |
| `action` | `lesson` — the recommended behavior |
| `confidence` | `confidence` — reliability estimate (0–1) |
| `category` | `category` — friction type |
| `applications` | `evidence` — count of supporting observations |
| `successes` | count of successful entries in `validation_history.json` |
| `source` | `"session-observation"` — origin marker |

#### Export Report

When exporting, a summary report is printed:

```
Export Summary
==============
Output: stdout
Total instincts: 2
Filtered: 2
Exported: 2

Categories:
- structural: 1
- epistemic: 1

Top Instincts (by confidence):
1. Explanations, documentation (0.83)
2. Technical explanations, debugging (0.77)
```

---

### Model Agnostic
Works with any LLM/agent:
- Friction detection applies to any output
- Reflection events stored as structured JSON
- Capability promotion uses evidence-based scoring
- Validation measures actual outcome improvement

---

## Mode Selection

```bash
# Explicit mode
ai-self-reflection --mode lightweight
ai-self-reflection --mode comprehensive

# Auto (recommended): lightweight for single tasks, comprehensive for learning sessions
ai-self-reflection --mode auto
```

**Auto logic:**
- Single task, no persistence needed → lightweight
- Multi-session, building capabilities → comprehensive
- Explicit `--mode` flag overrides auto

---

## Integration with Other Skills

1. **After complex tasks:** Run `record` (comprehensive) or post-hoc review (lightweight)
2. **Periodically:** Run `distill` to extract candidate lessons
3. **After validation:** Run `validate` to record capability improvement
4. **For visibility:** Run `report` for system state
5. **At runtime:** Run `bridge --scope` to inject capabilities as system prompt constraints
6. **With `verification-before-completion`:** Evidence before claims
7. **With `systematic-debugging`:** Root cause analysis feeds reflection
8. **With `writing-skills`:** TDD for skill creation includes reflection

---

## Anti-patterns (Both Modes)
- **Performative Reflection** — "I notice elegant pattern" without operational value
- **Reflection Without Change** — "Could do better" without identifying what changes
- **Overfitting** — One failure creates permanent rule
- **Endless Analysis** — Reflection replaces execution

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 3.0.0 | 2026-08-03 | Unified lightweight (ai-self-reflection) + comprehensive (ai-improved-self-reflection) with tiered modes |
| 2.1.0 | 2026-07-15 | Comprehensive mode with CLI, promotion, bridge |
| 1.0.0 | 2026-07-01 | Lightweight operational protocol |

---

## License

MIT License — Use freely with your AI agents.