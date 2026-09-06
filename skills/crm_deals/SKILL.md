---
description: 'Get all deals attached to a contact in the CRM. Returns the deal list
  so you can see what opportunities are associated with a person without asking a
  rep.

  '
triggers:
- deals for contact
- contact deals
- what deals
- show deals
- list deals
tags:
- crm
- deals
- contacts
- lookup
risk_level: low
cost_multiplier: 0.5
inputs:
- name: contact_id
  type: string
  required: true
  default: null
name: crm_deals
---

# crm-deals

Get all deals associated with a contact in the CRM.

## When to use

Use this skill when you have a contact ID and need to see what deals are
attached to that person. It returns the full deal list so you never have to
ask a rep for deal information.

## How it works

1. Take the contact ID from the user or a previous CRM lookup
2. Call `deals_for_contact` on the repository with the contact ID
3. Return the list of deals (empty if none)

## Input

- `contact_id` (str, required): The CRM contact ID to look up deals for.

## Output

A dict with:
- `ok` (bool): True if successful, False if capability not enabled
- `deals` (list[dict]): List of deal objects, each with:
  - `id` (str): Deal ID
  - `name` (str): Deal name
  - `stage` (str): Deal stage
  - `amount` (float | null): Deal amount
  - `currency` (str): Currency code
  - `company` (dict): Company info with `id` and `name`
- `error` (str, optional): Present only if `ok` is False

## Notes

- Returns an empty list if the contact has no deals or doesn't exist.
- Requires the "crm" capability to be enabled.
- The repository is injectable for testing via `set_repository`.
