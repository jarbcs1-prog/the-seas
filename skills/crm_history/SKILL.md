---
description: 'Read the full CRM dossier for a contact including deals, email threads,
  meetings, engagement stats, and colleagues. Returns a structured history object
  so you never have to ask a rep for context. Free. Use it whenever you have a contact
  id and need their complete CRM timeline.

  '
triggers:
- crm history
- read crm history
- contact history
- contact dossier
- crm dossier
- contact timeline
- deal history
- email threads
- meeting history
tags:
- crm
- history
- contacts
- deals
- threads
- meetings
- dossier
risk_level: low
cost_multiplier: 0.5
inputs:
- name: contact_id
  type: string
  required: true
  default: null
- name: threads
  type: string
  required: false
  default: null
- name: messages_per_thread
  type: string
  required: false
  default: null
name: crm_history
---

# crm-history

Read the full CRM dossier for a contact.

## When to use

Use this skill whenever you have a contact id and need their complete CRM
timeline: deals, email threads, meetings, engagement stats, and colleagues.
It returns everything in one structured call so you never have to piece it
together from multiple searches.

## How it works

1. Take the contact id (from a prior `crm-search` or user input)
2. Call `read_crm_history` on the repository with the contact id
3. Return the full dossier as a structured object

## Input

- `contact_id` (str, required): The CRM contact ID to look up.
- `threads` (int, optional): Maximum number of email threads to return. Default 5.
- `messages_per_thread` (int, optional): Maximum messages per thread. Default 6.

## Output

A dict with:
- `ok` (bool): True if successful, False if capability gated or contact not found
- `history` (list): List containing one dossier dict with:
  - `contact`: { fullName, email, title, companyName, company }
  - `deals`: list of { id, name, stage, role, amount, currency, expectedCloseDate }
  - `threads`: list of { subject, messageCount, lastMessageAt, messages[] }
  - `meetings`: list of { title, startsAt, attended, attendees[] }
  - `stats`: { emails, theyReplied, lastReplyAt, meetings, nextMeetingAt }
  - `colleagues`: list of { id, name, title }
- `error` (str, optional): Error message if ok is False

## Notes

- Returns `ok: False` with an error if the contact id does not exist.
- The `threads` and `messages_per_thread` parameters let you control payload size.
- Requires the "crm" capability to be enabled.
