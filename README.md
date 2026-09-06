# S.E.A.S. Desktop — Demo Version

Self-Evolving Agentic System — agent orchestration, skills, and CRM intelligence demo.

## This is a DEMO CONFIGURATION folder

The actual codebase lives at: `F:\theseas`

This folder (`F:\the-seas`) contains wrapper scripts for easy demonstration of the key features.

---

## Quick Demo

```bash
# Run the CRM skills demonstration
python f:/theseas/scripts/demo_crm_skills.py

# Run the self-improvement protocol demonstration  
python f:/theseas/scripts/demo_self_improvement.py
```

---

## What Gets Demonstrated

### 1. CRM Skills Demo (`demo_crm_skills.py`)
- Search contacts, companies, deals by name/domain
- Full contact dossier assembly
- Company lookup by ID
- Deal retrieval for contacts
- Name parsing utility

**Verified working**: ✓ All 5 skills execute, 211 tests pass

### 2. Self-Improvement Protocol Demo (`demo_self_improvement.py`)
- `ai-self-reflection` CLI full cycle:
  1. `initialize` — create memory files
  2. `record` — log 3 friction observations
  3. `distill` — promote to candidate lessons
  4. `validate` — record 2 validations
  5. `promote` — promote to local adaptation
  6. `report` — system report
  7. `bridge` — generate capability constraints
  8. `instincts export` — export portable JSON

**Verified working**: ✓ Full cycle completes, capability advances from level 1 → 2

---

## Core Architecture

```
F:\theseas\
├── system/               # Python backend (core engine)
│   ├── api.py            # FastAPI REST server (port 8377)
│   ├── cli.py            # 60+ CLI commands
│   ├── crm_repository.py # MockCRM + real skill interface
│   ├── skill_registry.py # Dynamic skill discovery
│   ├── capabilities.py   # Env-gated external sources
│   └── persona_distiller.py  # Persona constraint generation
├── skills/               # 32 skills total
│   ├── ai-self-reflection/   # Tiered self-improvement
│   ├── crm_*/               # 18 CRM integration skills
│   └── ...                 # code-review, debugging, etc.
├── profiles/             # Agent profiles (crm-researcher, etc.)
└── scripts/              # Demo scripts
    ├── demo_crm_skills.py
    └── demo_self_improvement.py
```

---

## Requirements

```bash
pip install fastapi uvicorn httpx PyJWT redis stripe python-dotenv
```

Or simply:
```bash
pip install -r F:\theseas\requirements.txt
```

---

## Pushing to GitHub

```bash
# From the demo folder (this location)
git init
git remote add origin https://github.com/jarbcs1-prog/the-seas.git

# Or work from the main codebase and exclude demo-only files
cd F:\theseas
git add .
git commit -m "Initial commit: S.E.A.S. Desktop v1.0.0"
git push -u origin main
```

Recommended `.gitignore` additions for GitHub:
```
# Demo folder (reference only)
the-seas/

# Large data
*.sqlite
data/
logs/
```

---

## Demo Results

### CRM Skills
- ✓ `crm_search` — Find by Marchetti, fernhill.com, Starlink
- ✓ `crm_dossier` — Full contact profile with honest "not on file" notes
- ✓ `crm_company` — Company lookup by ID
- ✓ `crm_deals` — Deal retrieval
- ✓ `crm_names` — Name parsing

### Self-Improvement
- ✓ 3 observations recorded (same lesson, different tasks)
- ✓ `distill` → 1 candidate lesson (level 1)
- ✓ 2 validations → score 0.51 (≥ 0.5 threshold)
- ✓ `promote` → level 2 (Local Adaptation)
- ✓ `bridge` → outputs capability constraints
- ✓ `instincts export` → portable JSON

---

## License

MIT License — see `F:\theseas\LICENSE`