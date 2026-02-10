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
