---
description: 'Parse a raw person name string into structured components (firstName,
  lastName, fullName). Handles suffixes like "Jr.", "Sr.", "II", "III", multi-word
  last names (e.g., "van der Berg", "de la Cruz"), and normalizes whitespace. Free.
  Use whenever you need to split a name for CRM lookups, display, or matching.

  '
triggers:
- parse name
- split name
- name parts
- first name last name
- extract name
- normalize name
tags:
- crm
- names
- parsing
- contacts
risk_level: low
cost_multiplier: 0.1
version: 1.0.0
author: S.E.A.S.
license: MIT
inputs:
- name: query
  type: string
  required: true
  default: null
name: crm_names
---

# crm-names

Parse a raw person name string into structured components.

## When to use

Use this skill whenever you have a raw name string and need to extract
the first name, last name, and full name for CRM operations, display,
or matching. It handles common name formats including suffixes and
multi-word surnames.

## How it works

1. Take the user's raw name string
2. Clean and normalize whitespace
3. Detect and preserve common suffixes (Jr., Sr., II, III, IV, etc.)
4. Split into firstName (first word) and lastName (remaining words + suffix)
5. Return structured result with fullName preserved

## Input

- `query` (str, required): A raw name string. Examples:
  - `"Sarah Marchetti"` → firstName: "Sarah", lastName: "Marchetti"
  - `"John Smith Jr."` → firstName: "John", lastName: "Smith Jr."
  - `"Ada Lovelace"` → firstName: "Ada", lastName: "Lovelace"
  - `"Juan Carlos de la Cruz"` → firstName: "Juan", lastName: "Carlos de la Cruz"
  - `"Robert Downey Jr."` → firstName: "Robert", lastName: "Downey Jr."

## Output

A dict with:
- `ok` (bool): True if successful, False if CRM capability not enabled
- `firstName` (str): The parsed first name
- `lastName` (str): The parsed last name (includes suffix if present)
- `fullName` (str): The cleaned full name
- `error` (dict, optional): Present only if `ok` is False, contains
  capability unavailability details

## Notes

- Requires the "crm" capability to be enabled (environment variable `crm` set)
- Suffixes handled: Jr., Sr., II, III, IV, V, Junior, Senior, 2nd, 3rd, 4th, 5th
- Multi-word last names are preserved (everything after the first word)
- Whitespace is normalized (multiple spaces collapsed, trimmed)
- Empty input returns empty strings for all name fields
