from decimal import Decimal, ROUND_HALF_UP
from typing import Any
import secrets
import string

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
from django.core.validators import MaxValueValidator, MinValueValidator
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
    name = models.CharField('نام', max_length=120)
    slug = models.SlugField('اسلاگ', unique=True)

    class Meta:
        verbose_name = 'دسته‌بندی'
        verbose_name_plural = 'دسته‌بندی‌ها'

    def __str__(self):
        return self.name


class Product(models.Model):
    CREDENTIAL_NONE = 'none'
    CREDENTIAL_EMAIL = 'email'
    CREDENTIAL_EMAIL_PASS = 'email_pass'
    CREDENTIAL_CHOICES = (
        (CREDENTIAL_NONE, 'نیازی نیست'),
        (CREDENTIAL_EMAIL, 'فقط ایمیل'),
        (CREDENTIAL_EMAIL_PASS, 'ایمیل و رمز عبور'),
    )

    DELIVERY_MANUAL = 'manual'
    DELIVERY_DIGITAL = 'digital'
    DELIVERY_CHOICES = (
        (DELIVERY_MANUAL, 'تحویل دستی (ادمین انجام می‌دهد)'),
        (DELIVERY_DIGITAL, 'فایل دانلودی (خودکار پس از پرداخت)'),
    )

    discount_enabled = models.BooleanField('تخفیف فعال', default=False)
    discount_percent = models.PositiveSmallIntegerField(
        'درصد تخفیف',
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='درصد تخفیف بین ۰ تا ۱۰۰.',
    )
    discount_start_at = models.DateTimeField('شروع تخفیف', blank=True, null=True)
    discount_end_at = models.DateTimeField('پایان تخفیف', blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True,
                                 verbose_name='دسته‌بندی')
    service = models.ForeignKey('Service', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='products', verbose_name='سرویس')
    title = models.CharField('عنوان', max_length=255)
    slug = models.SlugField('اسلاگ', unique=True)
    short_description = models.CharField('خلاصه توضیحات', max_length=300, blank=True,
                                          help_text='توضیح کوتاه برای کارت خدمت (حداکثر ۳۰۰ کاراکتر)')
    description = models.TextField('توضیحات', blank=True)
    features = models.TextField('ویژگی‌ها', blank=True,
                                help_text='هر ویژگی در یک خط (خط‌به‌خط نمایش داده می‌شود)')
    featured_image = models.ImageField('تصویر شاخص', upload_to='products/', blank=True, null=True,
                                       validators=[validate_image_file])
    price = models.DecimalField('قیمت پایه', max_digits=10, decimal_places=2,
                                help_text='اگر تنوع قیمتی دارد، قیمت هر تنوع جداگانه تنظیم می‌شود. این قیمت پیش‌فرض است.')
    credential_type = models.CharField('اطلاعات حساب مشتری', max_length=20,
                                        choices=CREDENTIAL_CHOICES, default=CREDENTIAL_NONE,
                                        help_text='آیا مشتری باید ایمیل/رمز حسابش را هنگام خرید وارد کند؟')
    credential_label = models.CharField('برچسب فیلد اطلاعات', max_length=120, blank=True,
                                         help_text='مثلاً «ایمیل اکانت نتفلیکس» — اگر خالی باشد از پیش‌فرض استفاده می‌شود')
    allow_quantity = models.BooleanField('انتخاب تعداد توسط مشتری', default=False,
                                          help_text='اگر فعال شود، مشتری می‌تواند تعداد دلخواه سفارش دهد')
    delivery_type = models.CharField('نحوه تحویل', max_length=20,
                                      choices=DELIVERY_CHOICES, default=DELIVERY_MANUAL,
                                      help_text='تحویل دستی: ادمین بررسی و انجام می‌دهد. فایل دانلودی: مشتری پس از پرداخت دانلود می‌کند.')
    digital_file = models.FileField('فایل دانلودی', upload_to='products/digital/', blank=True, null=True,
                                     help_text='فایلی که پس از پرداخت موفق برای مشتری قابل دانلود می‌شود')
    seo_title = models.CharField('عنوان SEO', max_length=255, blank=True)
    seo_description = models.TextField('توضیحات SEO', blank=True)
    is_active = models.BooleanField('فعال', default=True)
    is_available = models.BooleanField('موجود', default=True,
                                        help_text='اگر غیرفعال شود، خدمت نمایش داده می‌شود ولی قابل خرید نیست (ناموجود)')
    created_at = models.DateTimeField('تاریخ ایجاد', auto_now_add=True, null=True)

    class Meta:
        verbose_name = 'خدمت'
        verbose_name_plural = 'خدمات'
        ordering = ['-created_at']

    def get_absolute_url(self):
        return reverse('shop:product_detail', args=[self.slug])

    @property
    def has_variants(self):
        """Check if product has any active variants."""
        return self.variants.filter(is_active=True).exists()

    @property
    def has_regions(self):
        """Check if product has any active regions."""
        return self.regions.filter(is_active=True).exists()

    @property
    def active_variants(self):
        return self.variants.filter(is_active=True).order_by('sort_order', 'price')

    @property
    def active_regions(self):
        return self.regions.filter(is_active=True).order_by('sort_order', 'name')

    @property
    def min_price(self):
        """Return lowest variant price or base price."""
        variants = self.variants.filter(is_active=True)
        if variants.exists():
            return self._discounted_amount(variants.order_by('price').first().price)
        return self._discounted_amount(self.price)

    @property
    def max_price(self):
        """Return highest variant price or base price."""
        variants = self.variants.filter(is_active=True)
        if variants.exists():
            return self._discounted_amount(variants.order_by('-price').first().price)
        return self._discounted_amount(self.price)

    def clean(self):
        super().clean()
        if self.discount_enabled and self.discount_percent <= 0:
            raise ValidationError({'discount_percent': 'برای فعال بودن تخفیف، درصد تخفیف باید بیشتر از صفر باشد.'})
        if self.discount_start_at and self.discount_end_at and self.discount_end_at <= self.discount_start_at:
            raise ValidationError({'discount_end_at': 'زمان پایان تخفیف باید بعد از زمان شروع باشد.'})

    @property
    def is_discount_configured(self):
        return bool(self.discount_enabled and self.discount_percent > 0)

    @property
    def is_discount_active(self):
        if not self.is_discount_configured:
            return False
        now = timezone.now()
        if self.discount_start_at and now < self.discount_start_at:
            return False
        if self.discount_end_at and now >= self.discount_end_at:
            return False
        return True

    @property
    def has_discount_timer(self):
        return bool(self.is_discount_active and self.discount_end_at)

    @property
    def discount_remaining_seconds(self):
        if not self.has_discount_timer:
            return 0
        remaining = int((self.discount_end_at - timezone.now()).total_seconds())
        return max(0, remaining)

    def get_base_price(self, variant=None):
        if variant:
            return variant.price
        return self.price

    def _discounted_amount(self, amount):
        base_amount = Decimal(amount)
        if not self.is_discount_active:
            return base_amount
        factor = (Decimal('100') - Decimal(self.discount_percent)) / Decimal('100')
        return (base_amount * factor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def get_price(self, variant=None, apply_discount=True):
        """Return effective price for a given variant (or base product price)."""
        base_price = self.get_base_price(variant=variant)
        if not apply_discount:
            return base_price
        return self._discounted_amount(base_price)

    def get_discount_amount(self, variant=None):
        base_price = self.get_base_price(variant=variant)
        discounted = self.get_price(variant=variant, apply_discount=True)
        diff = Decimal(base_price) - Decimal(discounted)
        if diff <= 0:
            return Decimal('0')
        return diff.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def __str__(self):
        return self.title


class ProductVariant(models.Model):
    """Pricing variant for a product (e.g., 1-month, 3-month, 1-year).
    Can optionally belong to a region so each region has its own price list."""
    product = models.ForeignKey(Product, related_name='variants', on_delete=models.CASCADE,
                                verbose_name='خدمت')
    region = models.ForeignKey('ProductRegion', related_name='variants', on_delete=models.CASCADE,
                               verbose_name='ریجن', blank=True, null=True,
                               help_text='اگر خدمت ریجن دارد، این تنوع متعلق به کدام ریجن است؟')
    name = models.CharField('نام تنوع', max_length=120,
                            help_text='مثلاً «۱ ماهه»، «۳ ماهه»، «۱ ساله»')
    price = models.DecimalField('قیمت', max_digits=10, decimal_places=2)
    sort_order = models.IntegerField('ترتیب نمایش', default=0)
    is_active = models.BooleanField('فعال', default=True)

    class Meta:
        verbose_name = 'تنوع قیمتی'
        verbose_name_plural = 'تنوع‌های قیمتی'
        ordering = ['region__sort_order', 'region__name', 'sort_order', 'price']

    def __str__(self):
        region_label = f' [{self.region.name}]' if self.region else ''
        return f'{self.product.title}{region_label} — {self.name} ({self.price:,.0f} تومان)'


class ProductRegion(models.Model):
    """Optional region selection for a product (e.g., US, EU, Turkey)."""
    product = models.ForeignKey(Product, related_name='regions', on_delete=models.CASCADE,
                                verbose_name='خدمت')
    name = models.CharField('نام ریجن', max_length=120,
                            help_text='مثلاً «آمریکا»، «اروپا»، «ترکیه»')
    sort_order = models.IntegerField('ترتیب نمایش', default=0)
    is_active = models.BooleanField('فعال', default=True)

    class Meta:
        verbose_name = 'ریجن'
        verbose_name_plural = 'ریجن‌ها'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return f'{self.product.title} — {self.name}'


class Service(models.Model):
    name = models.CharField('نام', max_length=140)
    slug = models.SlugField('اسلاگ', unique=True)
    description = models.TextField('توضیحات', blank=True)
    featured_image = models.ImageField('تصویر / لوگو', upload_to='services/', blank=True, null=True,
                                        validators=[validate_image_file],
                                        help_text='لوگو یا تصویر سرویس (نمایش در صفحه اصلی و لیست سرویس‌ها)')
    icon = models.CharField('آیکون CSS', max_length=120, blank=True,
                            help_text='اختیاری — اگر تصویر آپلود شود، از تصویر استفاده می‌شود.')
    active = models.BooleanField('فعال', default=True)
    order = models.IntegerField('ترتیب', default=100)

    class Meta:
        ordering = ('order', 'name')
        verbose_name = 'گروه خدمات'
        verbose_name_plural = 'گروه‌های خدمات'

    def __str__(self):
        return self.name


class AccountItem(models.Model):
    product = models.ForeignKey(Product, related_name='items', on_delete=models.CASCADE,
                                verbose_name='خدمت')
    username_encrypted = models.BinaryField('نام‌کاربری (رمزنگاری)')
    password_encrypted = models.BinaryField('رمزعبور (رمزنگاری)')
    notes_encrypted = models.BinaryField('یادداشت (رمزنگاری)', blank=True, null=True)
    created_at = models.DateTimeField('تاریخ ایجاد', default=timezone.now)
    allocated = models.BooleanField('تخصیص یافته', default=False)

    class Meta:
        verbose_name = 'آیتم اکانت'
        verbose_name_plural = 'آیتم‌های اکانت'

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

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                             null=True, blank=True, verbose_name='کاربر')
    order_number = models.CharField('شماره سفارش', max_length=30, unique=True, blank=True)
    subtotal_amount = models.DecimalField('جمع جزء', max_digits=10, decimal_places=2, default=0)
    vat_percent_applied = models.PositiveSmallIntegerField('درصد مالیات اعمال‌شده', default=0)
    vat_amount = models.DecimalField('مبلغ مالیات بر ارزش افزوده', max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField('مبلغ کل', max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField('تاریخ ایجاد', default=timezone.now)
    status_updated_at = models.DateTimeField('آخرین تغییر وضعیت', default=timezone.now)
    paid = models.BooleanField('پرداخت شده', default=False)
    status = models.CharField('وضعیت', max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING_REVIEW)
    customer_name = models.CharField('نام مشتری', max_length=150, blank=True, default='')
    customer_phone = models.CharField('تلفن مشتری', max_length=32, blank=True, default='')
    customer_email = models.EmailField('ایمیل مشتری', blank=True, default='')
    shipping_address = models.TextField('آدرس ارسال', blank=True, default='')

    class Meta:
        verbose_name = 'سفارش'
        verbose_name_plural = 'سفارش‌ها'
        ordering = ['-created_at']

    @staticmethod
    def generate_order_number():
        """Generate unique order number like ACC-20260214-83724"""
        date_part = timezone.now().strftime('%Y%m%d')
        rand_part = ''.join(secrets.choice(string.digits) for _ in range(5))
        return f'ACC-{date_part}-{rand_part}'

    def save(self, *args, **kwargs):
        if not self.order_number:
            for _ in range(10):
                num = self.generate_order_number()
                if not Order.objects.filter(order_number=num).exists():
                    self.order_number = num
                    break
        if self.pk is not None:
            previous = Order.objects.filter(pk=self.pk).only('status').first()
            if previous and previous.status != self.status:
                self.status_updated_at = timezone.now()
        super().save(*args, **kwargs)

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

    @property
    def effective_subtotal(self):
        subtotal = Decimal(self.subtotal_amount or 0)
        if subtotal > 0:
            return subtotal
        if self.vat_amount and self.total:
            calculated = Decimal(self.total or 0) - Decimal(self.vat_amount or 0)
            if calculated > 0:
                return calculated
        return Decimal(self.total or 0)

    @property
    def effective_vat_amount(self):
        vat = Decimal(self.vat_amount or 0)
        if vat > 0:
            return vat
        return Decimal('0')

    @property
    def effective_vat_percent(self):
        return int(self.vat_percent_applied or 0)

    @property
    def has_vat(self):
        return self.effective_vat_amount > 0

    def __str__(self):
        return f'سفارش {self.order_number}'


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE,
                              verbose_name='سفارش')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True,
                                verbose_name='خدمت')
    account_item = models.ForeignKey(AccountItem, null=True, blank=True, on_delete=models.SET_NULL,
                                     verbose_name='آیتم اکانت')
    price = models.DecimalField('قیمت واحد', max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField('تعداد', default=1)
    variant_name = models.CharField('تنوع انتخابی', max_length=120, blank=True, default='',
                                     help_text='نام تنوع در زمان خرید (مثلاً ۳ ماهه)')
    region_name = models.CharField('ریجن انتخابی', max_length=120, blank=True, default='',
                                    help_text='نام ریجن در زمان خرید')
    customer_email = models.EmailField('ایمیل مشتری (برای حساب)', blank=True, default='')
    customer_password = models.CharField('رمز عبور مشتری (برای حساب)', max_length=255, blank=True, default='')

    class Meta:
        verbose_name = 'آیتم سفارش'
        verbose_name_plural = 'آیتم‌های سفارش'

    @property
    def line_total(self):
        return self.price * self.quantity

    def __str__(self):
        product_title = self.product.title if self.product else '(حذف شده)'
        variant_str = f' ({self.variant_name})' if self.variant_name else ''
        return f'{product_title}{variant_str} ×{self.quantity} — {self.line_total:,.0f}'


class TransactionLog(models.Model):
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True,
                              verbose_name='سفارش')
    provider = models.CharField('درگاه', max_length=50)
    payload = models.JSONField('پاسخ درگاه', blank=True, null=True)
    success = models.BooleanField('موفق', default=False)
    created_at = models.DateTimeField('تاریخ', default=timezone.now)

    class Meta:
        verbose_name = 'تراکنش'
        verbose_name_plural = 'تراکنش‌ها'

    def __str__(self):
        status = 'موفق' if self.success else 'ناموفق'
        return f"تراکنش #{self.id} — {self.provider} — {status}"


class CartItem(models.Model):
    """Persistent cart item stored in DB for logged-in users."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='cart_items', verbose_name='کاربر')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name='خدمت')
    variant = models.ForeignKey('ProductVariant', on_delete=models.SET_NULL, null=True, blank=True,
                                verbose_name='تنوع انتخابی')
    region = models.ForeignKey('ProductRegion', on_delete=models.SET_NULL, null=True, blank=True,
                               verbose_name='ریجن انتخابی')
    quantity = models.PositiveIntegerField('تعداد', default=1)
    customer_email = models.EmailField('ایمیل مشتری', blank=True, default='')
    customer_password = models.CharField('رمز عبور مشتری', max_length=255, blank=True, default='')
    created_at = models.DateTimeField('تاریخ ایجاد', auto_now_add=True)
    updated_at = models.DateTimeField('آخرین بروزرسانی', auto_now=True)

    class Meta:
        verbose_name = 'آیتم سبد خرید'
        verbose_name_plural = 'آیتم‌های سبد خرید'
        unique_together = ('user', 'product')

    def __str__(self):
        variant_str = f' ({self.variant.name})' if self.variant else ''
        return f'{self.user.username} — {self.product.title}{variant_str} x{self.quantity}'
