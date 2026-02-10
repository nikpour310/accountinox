# Support CRM-lite Guide

This document describes the support CRM-lite features added to Accountinox.

## 1) Support Contacts Excel Export

Location: Django Admin -> `Support contacts`

Action: `Export selected contacts to Excel (.xlsx)`

Columns in export:
- `id`
- `name`
- `phone` (normalized)
- `created_at`
- `last_seen`
- `total_sessions`
- `total_messages_user`
- `total_messages_operator`
- `last_session_status` (`active`/`closed`)
- `last_message_at`

Permission required:
- superuser, or
- `support.can_export_support_contacts`

## 2) Customer Rating After Session Close

URL:
- `GET/POST /support/rate/<session_id>/`

Rules:
- rating is allowed only for closed sessions
- only one rating per session
- score must be between `1..5`
- if score is `1`, `reason` is required
- rating is linked to session agent (`assigned_to` fallback: `operator`, `closed_by`)

User flow:
- after session is closed, customer can submit rating
- if already submitted, page shows existing rating

## 3) Roles and Groups

Management command:

```bash
cd "f:/Python Projects/accountinox"
.venv/Scripts/python.exe manage.py setup_support_roles
```

Created groups:
- `Content Admin`
- `Support Agent`
- `CRM Admin`
- `Owner`

Notes:
- `Owner` gets full permissions
- `SupportRating` admin visibility:
  - Owner/superuser: all ratings
  - other staff users: only ratings where `agent == current user`

## 4) Session Reopen Behavior

When a session is closed and the same customer sends a new message:
- a new active `ChatSession` is created
- it appears again in operator active/unread lists
- unread badge counts only active sessions
