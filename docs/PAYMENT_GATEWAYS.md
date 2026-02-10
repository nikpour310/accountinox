# راهنمای درگاه‌های پرداخت (ZarinPal / Zibal)

Accountinox از دو درگاه پرداخت اصلی ایران پشتیبانی می‌کند: **ZarinPal** و **Zibal**.

## تنظیم محیط

### تنظیمات محلی (Sandbox)

برای تست محلی بدون اتصال به درگاه واقعی، از `payment_providers.py` استفاده کنید که مستقیماً:
- Requests را مOck می‌کند
- JSON responses را شبیه‌سازی می‌کند
- Transaction logs را ذخیره می‌کند

### تنظیمات Production

برای Production، کلیدهای Merchant ID را در `.env` قرار دهید:

```env
# Production: ZarinPal Merchant ID
ZARINPAL_MERCHANT_ID=your-merchant-id-from-zarinpal

# Production: Zibal Merchant ID
ZIBAL_MERCHANT_ID=your-merchant-id-from-zibal
```

## تست محلی Callback

### 1. شروع پرداخت

```bash
curl -X POST http://localhost:8000/shop/checkout/ \
  -d "product_id=1&gateway=zarinpal"
```

کاربر به درگاه‌ها هدایت می‌شود. در sandbox، می‌توانید مستقیماً callback کنید.

###  2. شبیه‌سازی Callback (Sandbox)

**ZarinPal Callback:**
```bash
curl "http://localhost:8000/shop/payment/callback/zarinpal/?Status=100&Authority=TEST_AUTHORITY_123&order_id=1"
```

**Zibal Callback:**
```bash
curl "http://localhost:8000/shop/payment/callback/zibal/?status=0&trackId=123456789&order_id=1"
```

جانب سرویس فروش:
- Payment verified شد ✓
- Order marked as paid
- Account items allocated شد

## ساختار داده‌ها

### TransactionLog

کل تراکنش‌ها در `TransactionLog` ذخیره شده‌اند:

```python
TransactionLog:
  - order: سفارش مرتبط
  - provider: 'zarinpal' | 'zibal'
  - payload: JSON (reference, amount, verify_result)
  - success: True/False
  - created_at: زمان ایجاد
```

### Order Statuses

```python
Order:
  - paid: False → True بعد از verification موفق
  - توزیع inventory: خودکار پس از paid=True
```

## تست‌های Mocked

تمام تست‌های payment با mocked requests طراحی شده‌اند و نیاز به اینترنت یا merchant ID ندارند:

```bash
pytest tests/test_payment.py -v
```

تست‌های شامل:
- ✓ ZarinPal initiate/verify موفق و نا موفق
- ✓ Zibal initiate/verify موفق و ناموفق
- ✓ Checkout order creation
- ✓ Callback verification و allocation
- ✓ Failure handling

## فعال‌سازی درگاه‌های واقعی

### 1. ZarinPal

- آدرس: https://zarinpal.com
- Sandbox: https://sandbox.zarinpal.com
- به Merchant ID نیاز است

```python
# config/settings.py یا .env
ZARINPAL_MERCHANT_ID='xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'
```

### 2. Zibal

- آدرس: https://zibal.ir
- Sandbox: https://sandbox.zibal.ir
- به Merchant ID نیاز است

```python
# config/settings.py یا .env
ZIBAL_MERCHANT_ID='your-zibal-merchant-id'
```

## تشخیص خرابی‌ها

### Payment verification failed
- ✗ Merchant ID نبود
- ✗ Authority/TrackId نامعتبر
- ✗ Amount mismatch

### Inventory not allocated
- ✓ تأکید کنید Transaction.success=True
- ✓ Order.paid=True

### Callback not received
- درگاه callback URL صحیح نیست
- قابل تست: `localhost` در sandbox نمی‌شود؛ از `ngrok` یا URL حقیقی استفاده کنید

## اطلاعات بیشتر

- [ZarinPal Docs](https://docs.zarinpal.com)
- [Zibal Docs](https://docs.zibal.ir)
- [Local Callback Testing with Ngrok](https://ngrok.com/download)
