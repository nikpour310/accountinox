# Accountinox

نسخهٔ ابتدایی پروژه فروش حساب‌های دیجیتال ساخته‌شده با Django.

ویژگی‌ها (خلاصه):
- احراز هویت ایمیل/پسورد، ورود گوگل (django-allauth)، ورود با شماره تلفن + OTP
- مدیریت محصولات، موجودی (آیتم‌های حساب)، سفارشات و تخصیص پس از پرداخت
- ادغام ساده با درگاه‌ها (ZarinPal و Zibal) از طریق adapter
- بلاگ با استخراج کلمات کلیدی و FAQ در هر پست
- پشتیبانی چت با ذخیره پیام‌ها و پنل مدیریت
- Tailwind با دو حالت CDN یا فایل محلی

شروع سریع (محلی):

1. ساخت محیط مجازی و نصب وابستگی‌ها:
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt

2. تنظیم متغیرها (فایل .env در ریشه)—نمونه در `.env.example`:
   ```
   DJANGO_SECRET_KEY=change-me
   DEBUG=1
   FERNET_KEY=<تولید شده از: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
   OTP_HMAC_KEY=<تولید شده از: python -c "import secrets; print(secrets.token_hex(32))">
   REDIS_URL=redis://localhost:6379/0  # optional; for production caching
   ```

3. اجرای مهاجرت‌ها و ایجاد کاربر:
   python manage.py migrate
   python manage.py seed_demo
   python manage.py createsuperuser

4. اجرای سرور توسعه:
   python manage.py runserver

## متغیرهای محیطی کلیدی

- **DJANGO_SECRET_KEY**: کلید مخفی Django (تولید یک رشتهٔ امن)
- **FERNET_KEY**: کلید رمزگذاری برای inventory items (از cryptography.Fernet)
- **OTP_HMAC_KEY**: کلید HMAC-SHA256 برای هش کد OTP. NOTE: In production (DEBUG=0) this is REQUIRED and the app will raise an error if it is not set. Generate with: `python -c "import secrets; print(secrets.token_hex(32))"`
- **REDIS_URL**: آدرس Redis برای caching و rate-limiting در production
- **DATABASE_URL**: MySQL برای cPanel (e.g., `mysql://user:pass@host/db`)
- **GOOGLE_CLIENT_ID / GOOGLE_SECRET**: برای ورود توسط گوگل
- **KAVENEGAR_API_KEY**: برای ارسال SMS (Provider: Kavenegar)
- **ZARINPAL_MERCHANT_ID**: Merchant ID از ZarinPal برای پرداخت
- **ZIBAL_MERCHANT_ID**: Merchant ID از Zibal برای پرداخت

## درگاه‌های پرداخت

برای راهنمای تنظیم ZarinPal و Zibal و تست محلی، فایل [docs/PAYMENT_GATEWAYS.md](docs/PAYMENT_GATEWAYS.md) را ببینید.

### Support Poll Endpoint

The long-poll endpoint for support accepts the following query parameters:

- `thread_id` (optional): numeric chat session id. If omitted the server will attempt to resolve the active session from the authenticated user or the request session cookie.
- `since` (optional, default=0): last message id received. Returns messages with id > `since`.
- `timeout` (optional, default=10): long-poll timeout in seconds.

Required parameters: none strictly required if the request can be matched to an active session (authenticated user or existing session cookie). Otherwise `thread_id` is required.
