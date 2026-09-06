---
description: 'Assemble a complete contact dossier from the CRM including email threads,
  meetings, deals, companies, and social handles. Returns plain-language notes for
  any missing data so the agent never invents information.

  '
triggers:
- contact dossier
- full dossier
- crm dossier
- read dossier
- get contact history
- contact history
- full contact
tags:
- crm
- dossier
- contacts
- history
- threads
- meetings
- deals
risk_level: low
cost_multiplier: 0.5
version: 1.0.0
author: S.E.A.S.
license: MIT
inputs:
- name: contact_id
  type: string
  required: false
  default: null
- name: name
  type: string
  required: false
  default: null
- name: email
  type: string
  required: false
  default: null
name: crm_dossier
---

# crm-dossier

Assemble a complete contact dossier from the CRM.

## When to use

Use this skill when you need the full picture on a contact — their email
threads, meetings, deals, company associations, and social handles. It
returns plain-language notes for any missing data so you never invent
information.

## How it works

1. Resolve the contact by `contact_id`, or by `name`/`email` via exact match
2. Call `full_dossier` on the repository
3. Return the dossier with notes for any empty sections

## Input

- `contact_id` (str, optional): The CRM contact ID. If provided, used directly.
- `name` (str, optional): Full name of the contact (used with exact_contacts lookup).
- `email` (str, optional): Email address of the contact (used with exact_contacts lookup).

At least one of `contact_id`, `name`, or `email` must be provided.

## Output

A dict with:
- `ok` (bool): True if successful
- `dossier` (dict, when ok=True): The full dossier containing:
  - `name`: Contact's full name
  - `email`: Contact's email
  - `handles`: List of social handles (platform, url, internal)
  - `threads`: List of email threads (subject, messageCount, lastMessageAt, messages)
  - `meetings`: List of meetings (title, startsAt, attended, attendees)
  - `deals`: List of deals (id, name, stage, amount, currency, company)
  - `companies`: List of companies (id, name, domain, industry)
  - `notes`: Plain-language notes for missing data (e.g., "No social handles are on file for X in the CRM.")
- `error` (dict, when ok=False): Error details with reason

## Notes

- If `name` or `email` matches multiple contacts, the skill returns an error asking for a `contact_id` to disambiguate.
- The `notes` field contains human-readable explanations for any empty sections — use these verbatim rather than guessing.
- Requires the `AGENT_BRIDGE_SECRET` capability (CRM session isolation).
