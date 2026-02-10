from django.conf import settings
from django.db import models
from django.utils import timezone
import hashlib
import hmac


class Profile(models.Model):
    user = models.OneToOneField('auth.User', on_delete=models.CASCADE)
    phone = models.CharField(max_length=32, blank=True, null=True)

    def __str__(self):
        return self.user.email


class PhoneOTP(models.Model):
    phone = models.CharField(max_length=32, unique=True)
    otp_hmac = models.CharField(max_length=256, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    last_sent_at = models.DateTimeField(default=timezone.now)
    attempts = models.IntegerField(default=0)
    locked_until = models.DateTimeField(blank=True, null=True)

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
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='order_addresses')
    label = models.CharField(max_length=80, blank=True, default='')
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=32)
    province = models.CharField(max_length=80)
    city = models.CharField(max_length=80)
    street_address = models.TextField()
    postal_code = models.CharField(max_length=20, blank=True, default='')
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', '-updated_at']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            OrderAddress.objects.filter(user=self.user).exclude(pk=self.pk).update(is_default=False)

    def __str__(self):
        label = f" ({self.label})" if self.label else ''
        return f'{self.full_name}{label}'
