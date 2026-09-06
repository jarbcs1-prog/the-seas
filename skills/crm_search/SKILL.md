---
description: 'Search the CRM for contacts, companies, and deals by name, email address,
  domain, or deal name. Returns each match with its id so you never have to ask a
  rep for one. Free. Use it whenever a question names a record you do not have the
  id for.

  '
triggers:
- search crm
- find contact
- find company
- find deal
- look up contact
- look up company
- look up deal
- crm search
- search for
- who is
tags:
- crm
- search
- contacts
- companies
- deals
- lookup
risk_level: low
cost_multiplier: 0.5
inputs:
- name: query
  type: string
  required: true
  default: null
- name: kinds
  type: string
  required: false
  default: null
- name: limit
  type: string
  required: false
  default: 10
name: crm_search
---

# crm-search

Search the CRM for contacts, companies, and deals.

## When to use

Use this skill whenever you need to look up a record in the CRM by name,
email, domain, or deal name and you don't have the id. It covers all three
record kinds: contacts, companies, and deals.

## How it works

1. Take the user's query (a name, email, domain, or deal name)
2. Call `search_crm` on the repository with the query
3. Return the results with a note if needed:
   - No results: say so explicitly, suggest trying a shorter or differently spelled term
   - Multiple results: name the candidates and ask which, never ask for an id
   - Single result: return it directly

## Input

- `query` (str, required): A name, email address, domain, or deal name. Minimum 2 characters.
- `kinds` (list[str], optional): Narrow the search to `contact`, `company`, or `deal`. Defaults to all three.
- `limit` (int, optional): Maximum results to return. Default 10, max 25.

## Output

A `SearchResult` with:
- `query`: the search term used
- `contacts`: list of `ContactHit` (id, name, title, email, company, lastActivityAt)
- `companies`: list of `CompanyHit` (id, name, domain, industry, contacts, deals)
- `deals`: list of `DealHit` (id, name, stage, amount, currency, company)
- `total`: total number of matches across all kinds
- `note`: guidance when zero or multiple results

## Notes

- Queries shorter than 2 characters return empty results immediately.
- Email addresses are matched case-insensitively.
- Domains are extracted from email addresses automatically.
- Results are scored by relevance and returned in order.
