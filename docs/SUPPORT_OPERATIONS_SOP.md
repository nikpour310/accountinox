# Support Operations SOP

## Objectives

- Keep response SLAs stable.
- Prevent unauthorized access to support sessions.
- Ensure every critical action is auditable.

## Daily Start Checklist (Operator)

1. Login with staff account and open `/support/operator/`.
2. Confirm queue summary (critical, unread, mine).
3. Confirm push status (if enabled) via `/support/push/debug/`.
4. Verify no active rate-limit warnings on the dashboard.

## Handling a Session

1. Open session from operator queue (auto-marks unread user messages).
2. Send a reply using either free text or approved quick replies.
3. If waiting on another team, update user with a clear ETA.
4. Close session only after user issue is resolved or user confirms closure.

## Security Rules

1. Never ask the customer for account passwords.
2. Do not share internal references or admin-only data in chat.
3. Treat ownership errors (`403`) as security events and report to engineering.
4. If repeated abuse is detected, escalate with timestamp + session id + IP evidence.

## Escalation Path

1. Payment mismatch/callback anomaly -> Engineering on-call.
2. Suspected account takeover or data leak -> Security incident process.
3. Queue latency spike -> Infra/Backend on-call.

## End-of-Shift Checklist

1. No critical unread sessions remain unassigned.
2. Session closures are up to date.
3. Any abnormal events are logged in incident notes.
