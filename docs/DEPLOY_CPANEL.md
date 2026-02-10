# استقرار در cPanel (راهنمای قدم‌به‌قدم)

## 🚀 شروع سریع (5 دقیقه)

اگر تجربه دارید، این ۵ دستور را اجرا کنید:

```bash
# 1️⃣ Clone یا آپلود پروژه
cd ~/public_html && git clone <repo> . 2>/dev/null || true

# 2️⃣ Activate virtualenv و نصب
source /home/username/virtualenv/public_html/bin/activate
pip install -r requirements.txt

# 3️⃣ Environment variables (`.env` یا Setup Python App)
cat > .env << 'EOF'
DEBUG=0
DJANGO_SECRET_KEY=$(python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DATABASE_URL=mysql://user:pass@localhost:3306/dbname
FERNET_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
OTP_HMAC_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
EOF

# 4️⃣ Database + static files
python manage.py migrate
python manage.py collectstatic --noinput

# 5️⃣ Restart Passenger
touch tmp/restart.txt
```

### ✅ Post-Deploy Checks

```bash
# بررسی صحت تنظیمات
curl https://yourdomain.com/                    # Hero page لود شود
curl https://yourdomain.com/healthz/            # {"status": "ok"}
curl -X POST https://yourdomain.com/support/send/  # 400 (CSRF expected without token)
```

### 🔧 Common Issues

| Issue | Fix |
|-------|-----|
| **500 - ALLOWED_HOSTS** | `ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com` در .env |
| **403 - Static files** | `python manage.py collectstatic --noinput` و check `settings.STATIC_URL/ROOT` |
| **400 - CSRF** | `CSRF_TRUSTED_ORIGINS=['https://yourdomain.com']` در .env (list کپی‌شود) |
| **SSL not working** | `SECURE_PROXY_SSL_HEADER=HTTP_X_FORWARDED_PROTO` در .env (cPanel proxy) |

---

## 📸 Media Files Serving (cPanel Production)

### تنظیم /media/ در cPanel

Passenger به‌طور خودکار `/media/` URLs را سرو نمی‌کند. دو روش:

**روش 1: Symlink + cPanel File Manager (ساده‌تر)**
```bash
# از طریق SSH یا Terminal در cPanel:
cd ~/public_html
ln -s ../media ./media

# سپس در cPanel File Manager:
# 1. Chmod 755 را برای media folder تنظیم کنید
# 2. Images در /home/username/media/ ذخیره خواهند شد
# 3. /media/ URL دسترسی خواهد داشت
```

**روش 2: Apache/cPanel Configuration**
- در cPanel → Addon Domains یا Main Domain
- اگر /media/ لود نشود، یک .htaccess اضافه کنید:

```apache
<Files "*.jpg">
    SetHeader Content-Type "image/jpeg"
</Files>
<Files "*.png">
    SetHeader Content-Type "image/png"
</Files>
<Files "*.webp">
    SetHeader Content-Type "image/webp"
</Files>
```

### Permissions (مهم!)

```bash
# Set permissions برای media folder
chmod 755 /home/username/media
chmod 644 /home/username/media/*  # Files readable
```

### Upload توسط Admin

- Django admin automatically خودکار `/media/products/` و `/media/blog/` را ایجاد می‌کند
- Files زیر ۵MB نمونه‌ی محدود (اختیاری validation اضافه کنید)

---

## 🔒 Image Upload Security

## مقدمه

این راهنما **Accountinox** را روی cPanel با Passenger (Python WSGI app server) و MySQL نصب می‌کند.

**پیش‌نیازها:**
- cPanel account فعال
- SSH access (اگر موجود باشد)
- MySQL یا آپشن پایگاه‌داده دیگر در cPanel
- Domain ثبت‌شده و اختصاص‌یافته

---

## G-1: تنظیم Passenger + Setup Python App

### مرحله 1: آپلود پروژه

1. بر روی cPanel وارد شوید
2. به **File Manager** بروید
3. پوشهٔ `public_html` را باز کنید
4. پروژه را آپلود کنید (یا از طریق Git/SSH):
   - اگر SSH دارید: `git clone https://repo-url.git public_html`
   - یا فایل‌ها را از طریق FTP آپلود کنید

**نتیجه:** پروژه در `/home/username/public_html/` قرار خواهد داشت

### مرحله 2: Python App Setup در cPanel

1. در cPanel، به **Setup Python App** بروید
2. **Create Application** را کلیک کنید
3. **Application root domain:** دامنهٔ خود را انتخاب کنید
4. **Python version:** Python 3.11 یا بالاتر انتخاب کنید
5. **Application path:** `/home/username/public_html` تنظیم کنید
6. **Application startup file:** `config/wsgi.py` تنظیم کنید
7. **Application entry point:** `application` تنظیم کنید
8. **Create** را کلیک کنید

**نتیجه:** cPanel یک virtualenv خودکار ایجاد می‌کند و Passenger فعال می‌شود

### مرحله 3: نصب وابستگی‌ها درون virtualenv

در **Terminal** در cPanel یا SSH:

```bash
# تغیر دایرکتوری
cd /home/username/public_html

# Activate virtualenv (مسیر آن را از Setup Python App یادداشت کنید)
source /home/username/virtualenv/public_html/bin/activate

# نصب requirements
pip install --upgrade pip
pip install -r requirements.txt
```

### مرحله 4: تنظیم متغیرهای محیطی

**روش 1 (توصیه‌شده): از طریق Setup Python App**
- در صفحهٔ Python App در cPanel، در قسمت **Environment Variables**:

```
DJANGO_SECRET_KEY=<generate-a-secure-key>
DEBUG=0
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DATABASE_URL=mysql://user:password@localhost:3306/dbname
FERNET_KEY=<generate-fernet-key>
OTP_HMAC_KEY=<generate-hmac-key>
GOOGLE_CLIENT_ID=<your-google-client-id>
GOOGLE_SECRET=<your-google-secret>
KAVENEGAR_API_KEY=<your-kavenegar-api-key>
REDIS_URL=
SECURE_PROXY_SSL_HEADER=HTTP_X_FORWARDED_PROTO
```

**روش 2: فایل .env**
- در `/home/username/public_html/.env` بسازید:

```bash
cat > .env << 'EOF'
DJANGO_SECRET_KEY=<generate-a-secure-key>
DEBUG=0
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DATABASE_URL=mysql://user:password@localhost:3306/dbname
FERNET_KEY=<generate-fernet-key>
OTP_HMAC_KEY=<generate-hmac-key>
GOOGLE_CLIENT_ID=<your-google-client-id>
GOOGLE_SECRET=<your-google-secret>
KAVENEGAR_API_KEY=<your-kavenegar-api-key>
EOF
```

**تولید کلیدهای امن:**

```bash
# تولید DJANGO_SECRET_KEY
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# تولید FERNET_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# تولید OTP_HMAC_KEY
python -c "import secrets; print(secrets.token_hex(32))"
```

### مرحله 5: بازگذاری پایگاه‌داده

```bash
cd /home/username/public_html

# Activate virtualenv
source /home/username/virtualenv/public_html/bin/activate

# اجرای migrations
python manage.py migrate

# جمع‌آوری static files
python manage.py collectstatic --noinput

# (اختیاری) ایجاد superuser
python manage.py createsuperuser
```

### مرحله 6: تنظیم مسیرهای Static و Media

**Static Files Mapping:**

1. در cPanel، به **Public HTML** بروید
2. `staticfiles/` پوشهٔ موجود برای static files
3. مطمئن شوید که Passenger به این پوشه دسترسی دارد

**Media Files:**

1. `media/` پوشه برای آپلوداهای کاربری (لوگو، تصاویر، etc.)
2. اطمینان دهید که پوشه writable است:
```bash
chmod 755 /home/username/public_html/media
```

**اگر Tailwind در local mode است:**

```bash
# Static files بازساختی کنید
python manage.py collectstatic --noinput

# مطابقت با `STATIC_ROOT/tailwind.min.css` (یا مشابه)
```

### مرحله 7: HTTPS و SSL

1. در cPanel، به **AutoSSL** یا **Let's Encrypt** بروید
2. SSL certificate را نصب کنید
3. Redirect HTTP به HTTPS را فعال کنید

---

## G-2: تنظیمات امنیتی و Production

### DEBUG=0 (اجباری)

در production، `DEBUG` باید **0** باشد:

```
DEBUG=0
```

اگر DEBUG=1 باشد:
- ❌ Sensitive secrets در error pages نشان داده می‌شود
- ❌ Static files خودکار سرو نمی‌شود

### ALLOWED_HOSTS - کنترل دسترسی

```
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com,ip.address.if.needed
```

**اگر ALLOWED_HOSTS غلط تنظیم شود:**
- ❌ 400 Bad Request برای درخواست‌های غیرمطابق

### CSRF Safety

```
CSRF_COOKIE_SECURE=True          # فقط HTTPS
CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

### SSL/HTTPS Redirect (پشت proxy/CDN)

اگر پشت proxy (CloudFlare, cPanel proxy) باشید:

```
SECURE_PROXY_SSL_HEADER=HTTP_X_FORWARDED_PROTO
SECURE_SSL_REDIRECT=True
```

**اگر مستقیم‌ باشید (بدون proxy):**

```
SECURE_SSL_REDIRECT=True
```

### Secure Cookies

```
SESSION_COOKIE_SECURE=True       # فقط HTTPS
CSRF_COOKIE_SECURE=True          # فقط HTTPS
SESSION_COOKIE_HTTPONLY=True     # جاوااسکریپت نمی‌تواند دسترسی داشته باشد
CSRF_COOKIE_HTTPONLY=True
```

### HSTS (HTTP Strict Transport Security)

```python
# config/settings.py - محتاط باشید! اول بدون این روشن کنید
if not DEBUG:
    SECURE_HSTS_SECONDS = 63072000  # 2 سال
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = False  # اول False بگذارید
```

**اخطار:** HSTS cache می‌شود. اگر اشتباه تنظیم شود، کلیشه‌ای می‌کند. ابتدا با SECURE_HSTS_SECONDS=3600 (1 ساعت) شروع کنید.

### Logging (بدون لو رفتن secrets)

```python
# config/settings.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/home/username/public_html/logs/django.log',
            'maxBytes': 1024*1024*5,  # 5MB
            'backupCount': 5,
            'formatter': 'simple',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'ERROR',
            'propagate': True,
        },
    },
    'formatters': {
        'simple': {
            'format': '{levelname} {asctime} {name} {message}',
            'style': '{',
        },
    },
}
```

---

## G-3: Static و Media Files

### Static Files Collection

```bash
cd /home/username/public_html
source /home/username/virtualenv/public_html/bin/activate

# Collect all static files
python manage.py collectstatic --noinput --clear

# نتیجه: تمام static در `staticfiles/` دسترسی‌پذیر می‌شود
```

### Tailwind چک‌کردن

```bash
# اگر Tailwind local mode است:
ls -la staticfiles/ | grep -i tailwind

# صفحه‌ای را تصدیق بزنید (view source → check CSS loaded)
```

### Media Upload

```bash
# مطمئن شوید permissions صحیح است
chmod 755 /home/username/public_html/media
chmod 755 /home/username/public_html/media/logos  # اگر این دایرکتوری وجود دارد

# لوگو/تصاویر را آپلود کنید (یا از طریق admin)
```

---

## G-4: Healthcheck Endpoint

یک endpoint سبک برای مراقبت سرور:

### مرحله 1: urls میں healthcheck

```python
# config/urls.py - اضافه کنید:

from django.views import View
from django.http import JsonResponse
from django.utils.decorators import csrf_exempt

@csrf_exempt
def healthcheck(request):
    """Lightweight health check endpoint for monitoring"""
    return JsonResponse({
        'status': 'ok',
        'database': 'connected',
        'timestamp': str(datetime.now())
    })

urlpatterns = [
    path('healthz/', healthcheck, name='healthcheck'),
    # ... باقی URLs
]
```

### مرحله 2: تست

```bash
curl https://yourdomain.com/healthz/
# نتیجه مورد انتظار: {"status": "ok", "database": "connected", ...}
```

### مرحله 3: Monitoring Setup

cPanel یا هر سرویس مراقبتی دیگر:
- هر 5 دقیقه GET request به `/healthz/` بفرستد
- اگر وضعیت !=200، الرت بدهد

---

## G-5: Production Environment Checklist

### الزامی (Mandatory)

- [ ] `DEBUG=0` در production
- [ ] `DJANGO_SECRET_KEY=<secure-random-string>` تنظیم شده
- [ ] `FERNET_KEY` برای encryption تنظیم شده
- [ ] `OTP_HMAC_KEY` برای OTP security تنظیم شده
- [ ] `ALLOWED_HOSTS` شامل دومنهٔ شما
- [ ] `SECURE_SSL_REDIRECT=True` (HTTPS فعال)
- [ ] Static files جمع‌آوری‌شده (`python manage.py collectstatic --noinput`)
- [ ] Migrations اجرا‌شده (`python manage.py migrate`)
- [ ] Database credentials در متغیرهای محیطی (نه در کد!)

### پایگاه‌داده (Database)

- [ ] MySQL user و password تنظیم‌شده
- [ ] `DATABASE_URL` به صورت `mysql://user:pass@host:port/dbname` تنظیم شده
- [ ] جداول ایجاد‌شده (`migrate`)

### سرویس‌های بیرونی (External Services)

- [ ] `GOOGLE_CLIENT_ID` و `GOOGLE_SECRET` (اگر Google login فعال است)
- [ ] `KAVENEGAR_API_KEY` (اگر SMS فعال است)
- [ ] Email SMTP credentials (اگر notification فعال است)

### SSL/HTTPS

- [ ] SSL certificate نصب‌شده (Let's Encrypt)
- [ ] HTTP redirect به HTTPS فعال
- [ ] `SECURE_PROXY_SSL_HEADER` (اگر پشت proxy است)

### Logging و Monitoring

- [ ] Logs directory writable است و accessible
- [ ] Healthcheck endpoint فعال (`/healthz/`)
- [ ] Error emails configured (اگر موجود باشد)

### Updates to .env.example

```bash
# .env.example - اطمینان دهید که تمام موارد موجود هستند:

DJANGO_SECRET_KEY=change-me
DEBUG=0
ALLOWED_HOSTS=yourdomain.com
DATABASE_URL=mysql://user:pass@localhost:3306/dbname

# Security & Encryption
FERNET_KEY=<from: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
OTP_HMAC_KEY=<from: python -c "import secrets; print(secrets.token_hex(32))">

# SSL/HTTPS (اگر پشت proxy)
SECURE_PROXY_SSL_HEADER=HTTP_X_FORWARDED_PROTO
SECURE_SSL_REDIRECT=1

# Social & SMS
GOOGLE_CLIENT_ID=
GOOGLE_SECRET=
KAVENEGAR_API_KEY=

# Redis (اختیاری)
REDIS_URL=redis://localhost:6379/0

# Email (اختیاری)
EMAIL_HOST=
EMAIL_PORT=
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
```

---

## Common Issues & Troubleshooting

### 400 Bad Request (ALLOWED_HOSTS Error)

```
Bad Request: /path/
```

**حل:**
```
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
```

### 500 Internal Server Error (Static not loading)

```
ModuleNotFoundError: No module named 'X'
```

**حل:**
1. Virtualenv activate شده؟
2. `pip install -r requirements.txt` موفق بود؟
3. Passenger restarted؟

### 403 Forbidden (Static/Media Permission)

```
Permission denied: /home/username/public_html/static/
```

**حل:**
```bash
chmod 755 /home/username/public_html/staticfiles
chmod 755 /home/username/public_html/media
```

### Static Files Not Loading

CSS/JS در browser نشان نمی‌دهد.

**حل:**
```bash
python manage.py collectstatic --noinput --clear
# پھر Passenger restart:
# cPanel → Setup Python App → Restart
```

### Passenger Restart

```bash
# SSH یا Terminal:
mkdir -p /home/username/public_html/tmp
touch /home/username/public_html/tmp/restart.txt
```

---

## بعدی: تست در production

```bash
# تست connectivity:
curl https://yourdomain.com/

# تست healthcheck:
curl https://yourdomain.com/healthz/

# تست static:
curl https://yourdomain.com/static/style.css

# تست admin (اگر دسترسی public):
curl https://yourdomain.com/admin/
```

---

## Support Push Notifications (Web Push)

### Required ENV

Add these variables in cPanel Python App env (or `.env`):

```bash
SUPPORT_PUSH_ENABLED=1
VAPID_PUBLIC_KEY=...
VAPID_PRIVATE_KEY=...
VAPID_SUBJECT=mailto:you@example.com
```

### Generate VAPID keys (Python)

Run inside the same virtualenv as Django:

```bash
python - <<'PY'
import base64
from cryptography.hazmat.primitives.asymmetric import ec

private_key = ec.generate_private_key(ec.SECP256R1())
private_num = private_key.private_numbers().private_value.to_bytes(32, "big")
private_b64 = base64.urlsafe_b64encode(private_num).rstrip(b"=").decode()

public_numbers = private_key.public_key().public_numbers()
public_raw = b"\x04" + public_numbers.x.to_bytes(32, "big") + public_numbers.y.to_bytes(32, "big")
public_b64 = base64.urlsafe_b64encode(public_raw).rstrip(b"=").decode()

print("VAPID_PUBLIC_KEY=" + public_b64)
print("VAPID_PRIVATE_KEY=" + private_b64)
PY
```

### HTTPS requirement

Web Push only works on HTTPS origins (or localhost in development).
For production on cPanel:

1. Enable SSL certificate for the domain.
2. Keep `SECURE_SSL_REDIRECT=1`.
3. If behind reverse proxy/CDN, set `SECURE_PROXY_SSL_HEADER`.

### cPanel static serving note

Service Worker source file is `static/sw.js` and Django also serves it at `/sw.js`.
After every deployment run:

```bash
python manage.py collectstatic --noinput
touch tmp/restart.txt
```

Then verify both paths:

```bash
curl -I https://yourdomain.com/sw.js
curl -I https://yourdomain.com/static/sw.js
```

If you use reverse proxy/CDN, keep `/sw.js` uncached for long periods (or purge cache after deploy) so browser gets latest worker quickly.
