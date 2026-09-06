---
description: 'Look up a company by its CRM id, or find all companies at a given domain.
  Returns the company record(s) with all fields so you never have to ask a rep for
  an id. Free. Use it whenever you have a company id or a domain and need the full
  company record.

  '
triggers:
- lookup company
- find company
- company by id
- company by domain
- companies at domain
- crm company
tags:
- crm
- company
- lookup
- domain
risk_level: low
cost_multiplier: 0.5
inputs:
- name: company_id
  type: string
  required: false
  default: null
- name: domain
  type: string
  required: false
  default: null
name: crm_company
---

# crm-company

Look up a company by its CRM id, or find all companies at a given domain.

## When to use

Use this skill when you have a company id (e.g. from a previous search or
a deal/contact record) and need the full company record, or when you have
a domain (e.g. "acme.com") and want to find all companies in the CRM at
that domain.

## How it works

1. Take either a `company_id` or a `domain` (not both)
2. Call the appropriate repository method:
   - `company_by_id` for exact id lookup
   - `companies_by_domain` for domain search
3. Return the company record(s) wrapped in a standard result

## Input

- `company_id` (str, optional): A company id to look up exactly. Provide this OR domain.
- `domain` (str, optional): A domain to search for companies (e.g. "acme.com"). Provide this OR company_id.

Exactly one of `company_id` or `domain` must be provided.

## Output

If `company_id` provided:
- `ok`: true
- `company`: dict with all company fields (id, name, domain, description, logoUrl, logoDarkUrl, iconUrl, iconDarkUrl, iconTone, brandColor, industry, subIndustry, city, stateCode, country, countryCode, phone, email, linkedinUrl, twitterUrl, githubUrl, pricingUrl, careersUrl, contacts, deals)

If `domain` provided:
- `ok`: true
- `companies`: list of company dicts (same fields as above)

If neither or both provided:
- `ok`: false
- `error`: descriptive message

If CRM capability not enabled:
- `ok`: false
- `error`: unavailability dict with reason

## Notes

- The CRM capability ("crm") must be enabled (AGENT_BRIDGE_SECRET set) for this skill to work.
- Domain matching is case-insensitive and exact.
- Company id lookup is exact match.
- Returns all COMPANY_FIELDS from the repository.
