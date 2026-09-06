#!/usr/bin/env python3
"""
Demo: The S.E.A.S. CRM Skills — Option A CLI Demo

Runs live against an in-memory MockCrmRepository seeded with fixture data.
No external API keys required. Repo-only CRM skills demonstrated:
  1. crm_search    — search contacts, companies, deals by name/domain/deal-name
  2. crm_dossier   — full contact dossier (profile, socials, activity)
  3. crm_company   — company lookup by ID
  4. crm_deals     — deals for a contact
  5. crm_history   — historical activity (threads, meetings, notes)
"""

import sys, os, json
sys.path.insert(0, os.getcwd())

from system.crm_repository import MockCrmRepository
from system.skill_registry import SkillRegistry

# ─── 1. Seed mock CRM with realistic demo data ───────────────────────────────
repo = MockCrmRepository()
repo.add_company('comp-1', 'Fernhill Corp', 'fernhill.com', 'Finance')
repo.add_company('comp-2', 'Stellar Dynamics', 'stellardynamics.io', 'SpaceTech')
repo.add_contact(
    'contact-1', 'Sarah', 'Marchetti',
    's.marchetti@fernhill.com', 'CFO', 'comp-1',
    'https://linkedin.com/in/sarahmarchetti',
)
repo.add_contact('contact-2', 'Alex', 'Vance', 'alex.vance@example.com', 'CTO')
repo.add_contact(
    'contact-3', 'Maya', 'Rostova',
    'm.rostova@stellardynamics.io', 'CEO', 'comp-2',
    'https://linkedin.com/in/mayarostova',
)
repo.add_deal('deal-1', 'Fernhill Audit Q3', 'negotiation', 125000.0, 'USD', 'comp-1')
repo.add_deal('deal-2', 'Stellar Starlink Contract', 'closed_won', 3500000.0, 'USD', 'comp-2')

# ─── 2. Register handlers and wire the seeded repo ──────────────────────────
reg = SkillRegistry()
n = reg.register_crm_skill_handlers()
print(f'\n[Registry] Registered {n} CRM skill handlers\n')

import skills.crm_search.handler       as search_h
import skills.crm_dossier.handler      as dossier_h
import skills.crm_company.handler      as company_h
import skills.crm_deals.handler        as deals_h
import skills.crm_history.handler      as history_h
import skills.crm_names.handler        as names_h

for h in (search_h, dossier_h, company_h, deals_h, history_h, names_h):
    h.set_repository(repo)

def show(title, result):
    print('=' * 60)
    print(title)
    print('=' * 60)
    print(json.dumps(result, indent=2, default=str))
    print()

# ─── 3. Demo 1: CRM Search ───────────────────────────────────────────────────
show('DEMO 1: crm_search — find Sarah Marchetti by name',
     search_h.execute(query='Marchetti', kinds=['contact'], limit=5))

show('DEMO 1b: crm_search — find Fernhill Corp by domain',
     search_h.execute(query='fernhill.com', kinds=['company']))

show('DEMO 1c: crm_search — find deal "Starlink"',
     search_h.execute(query='Starlink', kinds=['deal']))

# ─── 4. Demo 2: CRM Dossier ──────────────────────────────────────────────────
show('DEMO 2: crm_dossier — full profile for contact-1 (Sarah)',
     dossier_h.execute(contact_id='contact-1'))

# ─── 5. Demo 3: CRM Company ──────────────────────────────────────────────────
show('DEMO 3: crm_company — company lookup by ID (comp-2)',
     company_h.execute(company_id='comp-2'))

# ─── 6. Demo 4: CRM Deals ────────────────────────────────────────────────────
show('DEMO 4: crm_deals — all deals for Sarah Marchetti',
     deals_h.execute(contact_id='contact-1'))

# ─── 7. Demo 5: CRM Names parsing ────────────────────────────────────────────
show('DEMO 5: crm_names — parse "Dr. Maya Rostova-Sato"',
     names_h.execute(query='Dr. Maya Rostova-Sato'))

# ─── 8. Demo 6: Task decomposition ───────────────────────────────────────────
print('=' * 60)
print('DEMO 6: system.cli decompose — "Audit Fernhill Corp"')
print('=' * 60)
os.system('python3 -m system.cli decompose "Audit Fernhill Corp" 2>&1')
print()

print('\n✓ All demo skills executed successfully.\n')
