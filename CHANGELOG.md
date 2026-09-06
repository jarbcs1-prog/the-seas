# Changelog

## v1.0.0-demo - 2026-09-07

### Added
- Demo version of S.E.A.S. Desktop
- 7 core skills: ai-self-reflection, crm_search, crm_dossier, crm_company, crm_deals, crm_history, crm_names
- Full self-improvement protocol (observe → distill → validate → promote → bridge → export)
- Task decomposition with dependency graphs
- CRM repository with mock data
- Agent profile system (crm-researcher)

### Modified
- Streamlined skill registry (removed 25+ unused skills)
- Removed Docker configuration (demo-focused)
- Removed Electron frontend (GUI not included in demo)

### Removed (for demo simplicity)
- Trading agents, OSINT connectors, voice agents
- Full supervisor/orchestrator stack
- Electron frontend

### Known Limitations
- All CRM data is in-memory mock (no persistence)
- External API skills require API keys (see INSTALL.md)
- No GUI/desktop app (CLI only)

## For Full Version

The complete S.E.A.S. Desktop at F:\theseas\ includes:
- Electron 43 + Svelte 5 frontend
- 18 CRM integration skills
- Multi-agent orchestration
- Trading, OSINT, voice capabilities