# OTP (یک‌بارمصرف) و راه‌اندازی IPPanel

این سند نحوهٔ فعال‌سازی و پیکربندی ارسال کدهای OTP با سرویس IPPanel (Edge) را در پروژهٔ Accountinox توضیح می‌دهد.

## خلاصهٔ قابلیت
- ارسال کد ۶ رقمی یک‌بارمصرف از طریق SMS
- ذخیرهٔ امن کد در مدل `PhoneOTP` به‌صورت HMAC-SHA256 (کلید در `OTP_HMAC_KEY`)
- محدودیت‌ها: انقضا (`otp_expiry_seconds`)، تعداد تلاش‌ها (`otp_max_attempts`) و cooldown ارسال مجدد (`otp_resend_cooldown`)
- رابط pluggable برای providerها در `apps/accounts/sms_providers.py` — شامل `console`, `kavenegar` و `ippanel`

## متغیرهای محیطی موردنیاز
- `IPPANEL_API_KEY` — کلید/توکن API برای IPPanel
- `IPPANEL_SENDER` — (اختیاری) فرستنده پیامک
- `IPPANEL_API_URL` — (اختیاری) آدرس API اگر متفاوت است

به‌صورت کلی این متغیرها را در `.env` قرار دهید یا در محیط سرور تنطیم کنید. نمونه در `.env.example` آمده است.

## فعال‌سازی
1. وارد بخش ادمین شوید (`/admin/`) و در `Site Settings` بخش `OTP / SMS`:
   - `OTP enabled` را فعال کنید
   - `SMS provider` را روی `IPPanel / Edge` قرار دهید
   - `SMS enabled` را روشن کنید
   - مقادیر `otp_expiry_seconds`, `otp_max_attempts`, `otp_resend_cooldown` را مطابق نیاز تنظیم کنید

2. در محیط سرور متغیرهای `IPPANEL_API_KEY` و (اختیاری) `IPPANEL_SENDER` را تنظیم کنید.

## نحوهٔ کار داخلی
- وقتی درخواست `POST /accounts/otp/send/` با پارامتر `phone` فرستاده شود:
  1. بررسی می‌شود که cooldown اجازهٔ ارسال دارد.
  2. کد تصادفی ۶ رقمی تولید و HMAC آن در `PhoneOTP.otp_hmac` ذخیره می‌شود.
  3. `sms_providers.get_sms_provider()` فراخوانی و متد `send_sms(phone, message)` اجرا می‌شود.

- پیاده‌سازی IPPanel در `apps/accounts/sms_providers.py` کلاس `IPPanelProvider` است که درخواست POST به IPPanel ارسال می‌کند. در این پیاده‌سازی از `urllib` استفاده شده تا هیچ وابستگی اضافه‌ای لازم نباشد.

## لاگ و مانیتورینگ
- به‌دلیل مسائل امنیتی، محتوای کد OTP هرگز در لاگ‌ها چاپ نمی‌شود؛ فقط وضعیت ارسال و شماره مقصد لاگ می‌شود.
- پیشنهاد: فعال‌سازی Sentry یا مانیتور لاگ‌های `apps` یا `accounts.sms` برای دیدن خطاهای ارسال پیامک.

## تست‌ها
- تست واحد نمونه برای provider در `tests/test_ippanel.py` اضافه شده است که `urlopen` را موک می‌کند.
- تست‌های جریان OTP در `tests/test_otp_flow.py` موجود است (expiry، resend/cooldown، و verify-login).

## نکات عملیاتی
- در محیط production مقدار `OTP_HMAC_KEY` حتماً تنظیم شود — اگر تنظیم نشود، برنامه در حالت `DEBUG=0` کرش خواهد کرد.
- برای ارسال واقعی پیامک از IPPanel، مطمئن شوید که شمارهٔ فرستنده و الگو (template) در سرویس IPPanel تنظیم شده باشد (در صورت نیاز به تنظیمات بیشتر در آن سمت).

## مشکلات شناخته‌شده و توسعهٔ آتی
- در آینده می‌توانید ارسال SMS را به صف (Celery/RQ) منتقل کنید تا retry و backoff مدیریت شود.
- افزودن support برای templates و localization پیامک (i18n) مفید است.
