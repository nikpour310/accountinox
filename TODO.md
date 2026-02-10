# Accountinox Support System TODO

Last updated: 2026-02-07

## Done
- Added support contact onboarding with required `name + phone` in `support/start/`.
- Added `SupportContact` model with unique phone and reuse/update logic.
- Added `ChatSession.contact` and `ChatSession.user_phone` snapshot fields.
- Kept long-polling chat flow and improved reopen behavior:
  - closing a session marks unread user messages as read;
  - if user sends after close, a new active session is created.
- Added operator thread route `support/operator/session/<id>/`.
- Fixed operator send endpoint behavior:
  - AJAX returns JSON;
  - non-AJAX form redirects to session view.
- Added push notification system for operator staff:
  - `SupportPushSubscription` endpoints subscribe/unsubscribe;
  - service worker support (`/sw.js`, `static/sw.js`);
  - push dispatch from user messages with payload (`title/body/url/thread_id/message_id`).
- Added online targeting for push:
  - `SupportOperatorPresence` model;
  - presence heartbeat endpoint;
  - push only to online staff in last 5 minutes;
  - skip push for operator already viewing same session.
- Added push debug endpoint `support/push/debug/` with:
  - `enabled`, `vapid_public_present`, `subs_count`, `active_subs`, `online_staff_count`, `last_error`.
- Added operator UX improvements:
  - dashboard active session list + unread banner;
  - standalone operator session view with polling, AJAX send, unread refresh;
  - fallback sound alert only when tab is hidden/unfocused;
  - localStorage toggle for notification sound.
- Added rate limit on operator send endpoint (`20/min`).
- Added support audit model/admin and event logging for:
  - send, close, open, subscribe, unsubscribe, push success/failure.
- Added/updated tests for:
  - start-chat validation and contact reuse;
  - reopen behavior after close;
  - operator send JSON/form flow;
  - unread behavior for active sessions;
  - online-only push dispatch and 410 disable behavior;
  - audit log creation.

## In Progress
- Manual browser QA on production-like mobile devices for operator session page.
- End-to-end push check on a real HTTPS domain (outside localhost).

## Open
- Optional WebSocket mode (behind feature toggle) for non-cPanel deployments.
- Optional richer operator alerts (sound pack and per-thread mute).
- Optional advanced audit dashboard (filters/charts/export).
