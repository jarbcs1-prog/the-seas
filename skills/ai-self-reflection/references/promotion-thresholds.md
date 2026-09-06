# Self-Improvement Promotion Thresholds

This reference documents the exact numeric thresholds used by the `promote` command to advance capabilities through the level hierarchy.

## Level Transitions

### Level 1 → Level 2 (Candidate Lesson → Local Adaptation)

**Prerequisites:** All must be true at promotion time.

| Metric | Minimum | Source |
|--------|---------|--------|
| `evidence` | 3 | Count of observations in `reflection_events.json` |
| `confidence` | 0.7 | Self-assessed reliability (0.0–1.0) |
| `validation_score` | 0.5 | EMA of validation outcomes |

**Calculation:**
- `validation_score` = exponential moving average of success (α = 0.3)
- First validation: `score = 0.3 * (1.0 - 0.0) = 0.3`
- Subsequent: `score = 0.3 * (outcome - old_score) + old_score`

**Example: Achieving promotion**
```bash
# Record 3 observations of same lesson
ai-self-reflection record --task "A" --category structural --observation "..." \
  --lesson "my pattern" --confidence 0.75 --evidence 1 --action "..."

ai-self-reflection record --task "B" --category structural --observation "..." \
  --lesson "my pattern" --confidence 0.80 --evidence 1 --action "..."

ai-self-reflection record --task "C" --category structural --observation "..." \
  --lesson "my pattern" --confidence 0.90 --evidence 1 --action "..."

# Distill → Candidate (evidence >= 3)
ai-self-reflection distill --min-evidence 2

# Validate twice to push score over 0.5
ai-self-reflection validate --capability "my pattern" --task "X" --outcome "..." --success --delta 0.05
ai-self-reflection validate --capability "my pattern" --task "Y" --outcome "..." --success --delta 0.05
# score now ≈ 0.455 + 0.3 * (1.0 - 0.455) = 0.56

# Promote → Local Adaptation
ai-self-reflection promote
```

### Level 2 → Level 3 (Local Adaptation → General Capability)

| Metric | Minimum |
|--------|---------|
| `evidence` | 5 |
| `confidence` | 0.8 |
| `validation_score` | 0.7 |

---

## Why These Thresholds?

### Evidence Threshold
- **Level 1→2: 3** — Minimum for pattern recognition without overfitting
- **Level 2→3: 5** — Ensures cross-context reliability before general defaults

### Confidence Threshold
- **Level 1→2: 0.7** — "Likely reliable" on 0–1 scale
- **Level 2→3: 0.8** — "Highly reliable" — influences agent defaults

### Validation Score Threshold
- Measures **outcome improvement**, not just self-assessment
- 0.5 = slight positive skew; 0.7 = consistently improving outcomes
- Prevents promotion on vanity metrics ("feels better") vs. actual results

---

## Debugging Failed Promotions

If `promote` reports 0 capabilities promoted:

1. Run `report` to see current values:
   ```json
   {
     "by_level": {"Candidate Lesson": 1},
     "top_capabilities": [{"confidence": 0.85, "validation_score": 0.3}]
   }
   ```

2. Check which threshold is blocking:
   - `confidence < 0.7` → need more confident self-assessment
   - `evidence < 3` → need more observations
   - `validation_score < 0.5` → need more successful validations

3. Use `bridge` to preview constraints:
   - Level 2+ capabilities appear in bridge output
   - Level 1 candidates do NOT appear