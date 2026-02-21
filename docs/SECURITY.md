# امنیت (خلاصه)

نکات مهم جهت آماده‌سازی برای محیط Production:

- استفاده از متغیرهای محیطی برای تمام اسرار (DJANGO_SECRET_KEY, DB credentials, FERNET_KEY, OTP_HMAC_KEY)
- DEBUG=0 در production
- فعال کردن HTTPS و HSTS
- کوکی‌ها: SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True
- غیر فعال کردن نمایش فهرست دایرکتوری در cPanel
- نگهداری کلیدهای رمزگذاری در محیط امن (در cPanel environment variables)
- محدودیت نرخ (rate-limiting) روی endpointهای auth/otp برای جلوگیری از brute-force
- لاگ‌برداری تغییرات حیاتی (admin actions, payment callbacks)

## OTP و لاگ‌برداری

- **کد OTP** هرگز در لاگ‌ها چاپ نمی‌شود — فقط destination و provider status لاگ‌شده‌اند.
- `OTP_HMAC_KEY` باید یک رشتهٔ امن و تصادفی باشد (می‌توان با `secrets.token_hex(32)` تولید کرد).
- اگر `OTP_HMAC_KEY` در production تعریف نشده باشد، fallback به `SECRET_KEY` استفاده خواهد شد (هشدار در log).
- صحه‌گذاری OTP از طریق HMAC-SHA256 and `hmac.compare_digest` انجام می‌شود تا از timing attacks جلوگیری شود.

## HTML واردشده (enamad و دیگر فیلدهای HTML)

- `enamad_html` از طریق ادمین قابل ویرایش است و عمداً با `|safe` در قالب رندر می‌شود تا مالک سایت بتواند اسکریپت/بدنهٔ رسمی را قرار دهد.
- این فیلد **فقط برای حساب‌های `staff` و superuser** در admin قابل ویرایش باشد.
- **هشدار XSS**: تنها HTML معتبر و رسمی (بدنهٔ ENAMAD، نوار کناری‌های اداری) را وارد کنید. HTML/JavaScript خطرناک می‌تواند کاربران را تهدید کند.

## 2026 Security Remediation Baseline

- Support chat ownership is now bound to a non-guessable public token (`ChatSession.public_token`) plus session ownership checks.
- Anonymous access to existing chat history is blocked unless the browser session owns the contact/session state.
- Support endpoints (`/support/send/`, `/support/messages/`, `/support/poll/`) are rate-limited and additionally protected against parallel poll floods per user/IP.
- Customer plaintext passwords were removed from checkout/cart/order paths and from Django admin inline views.
- Backup restore now validates archive paths before extraction to prevent Zip Slip path traversal.
- `FERNET_KEY` validation is fail-fast at startup when `REQUIRE_FERNET_KEY=1` (default in production).
- CI now enforces `python manage.py check --deploy --fail-level WARNING` and `pytest` as required gates.

## Incident Response Quick Steps

1. Contain: disable risky endpoint/feature flags (for support push/chat if needed) and preserve logs.
2. Scope: identify affected users/orders/sessions from `TransactionLog`, support audit logs, and web logs.
3. Eradicate: rotate `DJANGO_SECRET_KEY`, `FERNET_KEY`, `OTP_HMAC_KEY`, and payment credentials if exposure is suspected.
4. Recover: run integrity checks (`manage.py check --deploy`, smoke tests, payment callback checks) before reopening traffic.
5. Postmortem: record timeline, root cause, blast radius, and permanent controls.
