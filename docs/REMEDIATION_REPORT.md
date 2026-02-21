# Security and Reliability Remediation Report (Before/After)

## Window

- Baseline: pre-remediation (legacy support/payment handling)
- Current: after phased hardening changes in this branch

## KPI Summary

| KPI | Before | After |
|---|---|---|
| Support session identifier exposure | Numeric session IDs | Public random token (`public_token`) |
| Anonymous session hijack resistance | Weak (phone-only reuse risk) | Session ownership + token checks |
| Chat endpoint abuse controls | Basic rate-limit only | Rate-limit + per-session concurrent poll guard |
| Customer plaintext password storage | Present in cart/order flow | Removed from model, views, template, admin |
| Payment callback amount validation | Missing | Enforced (expected vs received) |
| Callback idempotency | Non-deterministic risk | Atomic, lock-based idempotent handling |
| Inventory allocation race resistance | Weak | `transaction.atomic` + `select_for_update` |
| Backup restore extraction safety | `extractall` without path guard | Zip Slip-safe extraction validation |
| Deployment security gate in CI | Not enforced | `check --deploy` + `pytest` required |

## Verification Evidence

- Test suite: `161 passed, 1 skipped`
- Migration dry-run: no new pending migrations
- Django checks: `python manage.py check` passes
- Deploy checks: `python manage.py check --deploy --fail-level WARNING` passes with CI env

## Residual Risk

- Production secret rotation remains an operational task (not automatic).
- Polling remains HTTP polling (improved), not full WebSocket/SSE migration.

## Recommended Next KPI Cycle

1. Track payment callback mismatch rate per provider.
2. Track support poll p95 latency and open connection count trend.
3. Track incident MTTR after runbook rollout.
