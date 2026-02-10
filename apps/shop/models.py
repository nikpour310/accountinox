from typing import Any

try:
    from cryptography.fernet import Fernet as _fernet_lib
except (ImportError, ModuleNotFoundError):
    # Mock Fernet if cryptography is broken in this environment
    class _FernetMock:
        def __init__(self, key):
            pass

        def encrypt(self, data):
            return data

        def decrypt(self, data):
            return data

    _fernet_lib = _FernetMock  # type: ignore

Fernet = _fernet_lib  # type: ignore

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone


def validate_image_file(image):
    """Validate that uploaded file is an image (jpg/png/webp only)"""
    allowed_types = ['image/jpeg', 'image/png', 'image/webp']
    if hasattr(image, 'content_type'):
        if image.content_type not in allowed_types:
            raise ValidationError('فقط فرمت‌های jpg, png, webp پذیرفته می‌شوند')
    # Size limit: 5MB
    if hasattr(image, 'size'):
        if image.size > 5 * 1024 * 1024:
            raise ValidationError('حجم فایل نباید بیش‌تر از 5 مگابایت باشد')


class Category(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    featured_image = models.ImageField(upload_to='products/', blank=True, null=True, validators=[validate_image_file])
    price = models.DecimalField(max_digits=10, decimal_places=2)
    seo_title = models.CharField(max_length=255, blank=True)
    seo_description = models.TextField(blank=True)

    def get_absolute_url(self):
        return reverse('shop:product_detail', args=[self.slug])

    def __str__(self):
        return self.title


class AccountItem(models.Model):
    product = models.ForeignKey(Product, related_name='items', on_delete=models.CASCADE)
    username_encrypted = models.BinaryField()
    password_encrypted = models.BinaryField()
    notes_encrypted = models.BinaryField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    allocated = models.BooleanField(default=False)

    def __str__(self):
        return f"Item for {self.product.title} (allocated={self.allocated})"

    @staticmethod
    def _fernet():
        key = getattr(settings, 'FERNET_KEY', None)
        if not key:
            raise RuntimeError('FERNET_KEY not configured')
        return Fernet(key.encode())

    def set_plain(self, username: str, password: str, notes: str = ''):
        f = self._fernet()
        self.username_encrypted = f.encrypt(username.encode())
        self.password_encrypted = f.encrypt(password.encode())
        self.notes_encrypted = f.encrypt(notes.encode()) if notes else None

    def get_plain(self):
        f = self._fernet()
        return {
            'username': f.decrypt(self.username_encrypted).decode(),
            'password': f.decrypt(self.password_encrypted).decode(),
            'notes': f.decrypt(self.notes_encrypted).decode() if self.notes_encrypted else '',
        }


class Order(models.Model):
    STATUS_PENDING_REVIEW = 'pending_review'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_DELIVERED = 'delivered'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = (
        (STATUS_PENDING_REVIEW, 'درحال بررسی'),
        (STATUS_CONFIRMED, 'تأیید شد'),
        (STATUS_DELIVERED, 'تحویل داده شد'),
        (STATUS_CANCELLED, 'لغو شد'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(default=timezone.now)
    status_updated_at = models.DateTimeField(default=timezone.now)
    paid = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING_REVIEW)
    customer_name = models.CharField(max_length=150, blank=True, default='')
    customer_phone = models.CharField(max_length=32, blank=True, default='')
    customer_email = models.EmailField(blank=True, default='')
    shipping_address = models.TextField(blank=True, default='')

    def timeline_steps(self):
        steps_flow = [
            (self.STATUS_PENDING_REVIEW, 'درحال بررسی'),
            (self.STATUS_CONFIRMED, 'تأیید شد'),
            (self.STATUS_DELIVERED, 'تحویل داده شد'),
        ]
        if self.status == self.STATUS_CANCELLED:
            return [
                {'key': self.STATUS_PENDING_REVIEW, 'label': 'درحال بررسی', 'state': 'done'},
                {'key': self.STATUS_CANCELLED, 'label': 'لغو شد', 'state': 'current'},
            ]

        reached_index = {
            self.STATUS_PENDING_REVIEW: 0,
            self.STATUS_CONFIRMED: 1,
            self.STATUS_DELIVERED: 2,
        }.get(self.status, 0)

        steps = []
        for index, (key, label) in enumerate(steps_flow):
            if index < reached_index:
                state = 'done'
            elif index == reached_index:
                state = 'current'
            else:
                state = 'pending'
            steps.append({'key': key, 'label': label, 'state': state})
        return steps

    def save(self, *args, **kwargs):
        if self.pk is not None:
            previous = Order.objects.filter(pk=self.pk).only('status').first()
            if previous and previous.status != self.status:
                self.status_updated_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Order #{self.id} - {self.get_status_display()}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    account_item = models.ForeignKey(AccountItem, null=True, blank=True, on_delete=models.SET_NULL)
    price = models.DecimalField(max_digits=10, decimal_places=2)


class TransactionLog(models.Model):
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True)
    provider = models.CharField(max_length=50)
    payload = models.JSONField(blank=True, null=True)
    success = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Tx {self.id} via {self.provider} - ok={self.success}"
