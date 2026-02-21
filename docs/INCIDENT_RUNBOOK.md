# Incident Runbook

## Scope

This runbook covers payment, support-chat, and security incidents in production.

## Immediate Response (0-30 min)

1. Acknowledge the incident in the ops channel and assign an incident commander.
2. Capture current time window and affected components.
3. Enable containment:
   - temporarily disable public chat entry points if abuse is ongoing,
   - pause payment settlement if callback anomalies are detected.
4. Preserve evidence:
   - application logs (`logs/django_error.log`, `logs/django_info.log`),
   - gateway callback payloads (`TransactionLog`),
   - support audit entries (`SupportAuditLog`).

## Triage (30-90 min)

1. Identify blast radius:
   - affected orders (`Order`, `TransactionLog`),
   - affected support sessions (`ChatSession`, `ChatMessage`).
2. Classify:
   - integrity issue (wrong paid status/allocation),
   - confidentiality issue (unauthorized data exposure),
   - availability issue (poll/worker saturation).
3. Decide rollback/forward-fix path.

## Recovery

1. Apply the fix to staging.
2. Run checks:
   - `python manage.py check --deploy --fail-level WARNING`
   - `python -m pytest -q`
3. Deploy to production with monitored rollout.
4. Validate:
   - payment callback success/failure paths,
   - support chat send/poll/ownership behavior,
   - error-rate and latency dashboards.

## Rollback Checklist

1. Keep latest backup artifact ready before migration/deploy.
2. If rollback is required:
   - redeploy last known good build,
   - restore DB/media backup if data corruption occurred,
   - rotate compromised credentials immediately.
3. Re-run smoke checks on critical routes (`checkout`, `payment_callback`, `support/poll`).

## Secret Rotation

Rotate on suspected exposure:

- `DJANGO_SECRET_KEY`
- `FERNET_KEY`
- `OTP_HMAC_KEY`
- payment gateway merchant credentials
- push keys (`VAPID_PRIVATE_KEY`) when applicable

## Post-Incident

1. Publish a timeline and root-cause analysis.
2. Document permanent preventive controls.
3. Add/adjust regression tests for the failure mode.
