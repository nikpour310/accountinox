from django.conf import settings
from django.db import models
from django.utils import timezone
import hashlib
import hmac


class Profile(models.Model):
    user = models.OneToOneField('auth.User', on_delete=models.CASCADE, verbose_name='کاربر')
    phone = models.CharField('شماره تلفن', max_length=32, blank=True, null=True)

    class Meta:
        verbose_name = 'پروفایل'
        verbose_name_plural = 'پروفایل‌ها'

    def __str__(self):
        return self.user.email


class PhoneOTP(models.Model):
    phone = models.CharField('شماره تلفن', max_length=32, unique=True)
    otp_hmac = models.CharField('کد HMAC', max_length=256, blank=True, null=True)
    created_at = models.DateTimeField('تاریخ ایجاد', default=timezone.now)
    last_sent_at = models.DateTimeField('آخرین ارسال', default=timezone.now)
    attempts = models.IntegerField('تلاش‌ها', default=0)
    locked_until = models.DateTimeField('قفل تا', blank=True, null=True)

    class Meta:
        verbose_name = 'کد OTP'
        verbose_name_plural = 'کدهای OTP'

    def _hmac(self, code: str) -> str:
        key = getattr(settings, 'OTP_HMAC_KEY', '')
        if not key:
            # fallback to SECRET_KEY (not recommended) if OTP_HMAC_KEY not set
            key = settings.SECRET_KEY
        hm = hmac.new(key.encode(), code.encode(), hashlib.sha256)
        return hm.hexdigest()

    def set_code(self, code: str):
        self.otp_hmac = self._hmac(code)
        now = timezone.now()
        self.created_at = now
        self.last_sent_at = now
        self.attempts = 0

    def check_code(self, code: str) -> bool:
        if not self.otp_hmac:
            return False
        return hmac.compare_digest(self.otp_hmac, self._hmac(code))

    def is_expired(self, expiry_seconds: int) -> bool:
        return (timezone.now() - self.created_at).total_seconds() > expiry_seconds

    def can_resend(self, cooldown_seconds: int) -> bool:
        return (timezone.now() - self.last_sent_at).total_seconds() >= cooldown_seconds

    def mark_sent(self):
        self.last_sent_at = timezone.now()

    def __str__(self):
        return f"OTP for {self.phone}"


class OrderAddress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='order_addresses', verbose_name='کاربر')
    label = models.CharField('برچسب', max_length=80, blank=True, default='')
    full_name = models.CharField('نام کامل', max_length=150)
    phone = models.CharField('تلفن', max_length=32)
    province = models.CharField('استان', max_length=80)
    city = models.CharField('شهر', max_length=80)
    street_address = models.TextField('آدرس')
    postal_code = models.CharField('کدپستی', max_length=20, blank=True, default='')
    is_default = models.BooleanField('آدرس پیش‌فرض', default=False)
    created_at = models.DateTimeField('تاریخ ایجاد', default=timezone.now)
    updated_at = models.DateTimeField('آخرین ویرایش', auto_now=True)

    class Meta:
        ordering = ['-is_default', '-updated_at']
        verbose_name = 'آدرس سفارش'
        verbose_name_plural = 'آدرس‌های سفارش'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            OrderAddress.objects.filter(user=self.user).exclude(pk=self.pk).update(is_default=False)

    def __str__(self):
        label = f" ({self.label})" if self.label else ''
        return f'{self.full_name}{label}'


class PendingProfileChange(models.Model):
    """Stores a pending phone or email change that requires OTP/code verification."""

    CHANGE_TYPE_CHOICES = [
        ('phone', 'شماره موبایل'),
        ('email', 'ایمیل'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='pending_changes', verbose_name='کاربر',
    )
    change_type = models.CharField('نوع تغییر', max_length=10, choices=CHANGE_TYPE_CHOICES)
    new_value = models.CharField('مقدار جدید', max_length=255)
    code_hmac = models.CharField('HMAC کد', max_length=256)
    created_at = models.DateTimeField('ایجاد', default=timezone.now)
    attempts = models.IntegerField('تلاش', default=0)

    class Meta:
        verbose_name = 'تغییر در انتظار تایید'
        verbose_name_plural = 'تغییرات در انتظار تایید'
        # Only one pending change per user per type at a time
        unique_together = ('user', 'change_type')

    def _hmac(self, code: str) -> str:
        key = getattr(settings, 'OTP_HMAC_KEY', '') or settings.SECRET_KEY
        return hmac.new(key.encode(), code.encode(), hashlib.sha256).hexdigest()

    def set_code(self, code: str):
        self.code_hmac = self._hmac(code)
        self.created_at = timezone.now()
        self.attempts = 0

    def check_code(self, code: str) -> bool:
        if not self.code_hmac:
            return False
        return hmac.compare_digest(self.code_hmac, self._hmac(code))

    def is_expired(self, seconds: int = 300) -> bool:
        return (timezone.now() - self.created_at).total_seconds() > seconds

    def __str__(self):
        return f'{self.get_change_type_display()} → {self.new_value} (user={self.user_id})'
