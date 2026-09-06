# Installation Guide — Demo Version

## Requirements

- **Python**: 3.12+ (tested with 3.14)
- **Node.js**: 26.x (optional, for frontend)
- **OS**: Windows 11, Linux, macOS

## Setup

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Verify installation
python3 -m system.cli skills

# 4. Run demos
python3 scripts/demo_crm_skills.py
python3 scripts/demo_self_improvement.py
```

## Running the API Server

```bash
python3 -m system.api --port 8377
# Visit http://localhost:8377/docs for Swagger UI
```

## Running the CLI

```bash
python3 -m system.cli --help
python3 -m system.cli skills
python3 -m system.cli decompose "Audit Fernhill Corp"
```

## Environment Variables (Optional)

| Variable | Purpose | Skills Enabled |
|----------|---------|----------------|
| RAPIDAPI_KEY | LinkedIn profile lookup | crm_linkedin |
| PERPLEXITY_API_KEY | Web research with citations | crm_lookup_socials, crm_perplexity |
| CONTEXT_DEV_API_KEY | Company brand/logo data | crm_enrich, crm_brand |