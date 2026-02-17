from pathlib import Path

from django.conf import settings
from django.db import models


class SiteSettings(models.Model):
    # ── عمومی ──────────────────────────────────────
    site_name = models.CharField('نام سایت', max_length=150, default='Accountinox')
    brand_wordmark_fa = models.CharField('نام فارسی برند', max_length=150, blank=True, default='اکانتینوکس')
    logo = models.ImageField('لوگو', upload_to='logos/', blank=True, null=True)
    site_description = models.TextField('توضیح سایت', blank=True, default='',
                                        help_text='توضیح کوتاه — نمایش در فوتر و متا تگ‌ها')

    # ── رنگ‌ها و ظاهر ──────────────────────────────
    primary_color = models.CharField('رنگ اصلی', max_length=7, default='#1ABBC8')
    secondary_color = models.CharField('رنگ ثانویه', max_length=7, default='#0468BD')
    accent_color = models.CharField('رنگ تاکیدی', max_length=7, default='#45E2CC')
    tailwind_mode = models.CharField('حالت Tailwind', max_length=10,
                                     choices=(('cdn', 'CDN'), ('local', 'فایل محلی')), default='cdn')

    # ── عناوین بخش‌های صفحه اصلی ──────────────────
    features_title = models.CharField('عنوان بخش ویژگی‌ها', max_length=120, blank=True,
                                      default='چرا اکانتینوکس؟')
    features_subtitle = models.CharField('زیرعنوان بخش ویژگی‌ها', max_length=250, blank=True,
                                         default='سادگی در خرید، سرعت در تحویل و اطمینان در کیفیت.')
    products_title = models.CharField('عنوان بخش محصولات', max_length=120, blank=True,
                                      default='جدیدترین محصولات')
    products_subtitle = models.CharField('زیرعنوان بخش محصولات', max_length=250, blank=True,
                                         default='محبوب‌ترین اکانت‌های پریمیوم با تحویل فوری.')

    # ── بخش CTA ────────────────────────────────────
    cta_title = models.CharField('عنوان CTA', max_length=120, blank=True,
                                 default='سوالی دارید؟ ما اینجاییم.')
    cta_description = models.CharField('توضیح CTA', max_length=300, blank=True,
                                       default='تیم پشتیبانی ما آماده پاسخگویی به تمام سوالات شماست.')
    cta_button1_text = models.CharField('دکمه ۱ CTA', max_length=60, blank=True, default='شروع گفتگو')
    cta_button1_url = models.CharField('لینک دکمه ۱ CTA', max_length=300, blank=True, default='/support/')
    cta_button2_text = models.CharField('دکمه ۲ CTA', max_length=60, blank=True, default='تماس با ما')
    cta_button2_url = models.CharField('لینک دکمه ۲ CTA', max_length=300, blank=True, default='/contact/')

    # ── فوتر ───────────────────────────────────────
    footer_copyright = models.CharField('متن کپی‌رایت', max_length=200, blank=True,
                                        default='تمامی حقوق محفوظ است.')
    footer_developer_name = models.CharField('نام توسعه‌دهنده', max_length=100, blank=True,
                                             default='رامین جلیلی')
    footer_developer_url = models.CharField('لینک توسعه‌دهنده', max_length=300, blank=True, default='')

    # ── اینماد و نمادها ────────────────────────────
    enamad_html = models.TextField('کد HTML اینماد', blank=True, default='',
                                   help_text='کد اینماد و سایر نمادهای اعتماد')

    # ── OTP / SMS ──────────────────────────────────
    SMS_PROVIDER_CHOICES = (
        ('console', 'Console (log only)'),
        ('kavenegar', 'Kavenegar'),
        ('ippanel', 'IPPanel / Edge'),
    )
    sms_provider = models.CharField('ارسال‌کننده SMS', max_length=100, blank=True, choices=SMS_PROVIDER_CHOICES, default='console', help_text='انتخاب سرویس ارسال پیامک')
    sms_enabled = models.BooleanField('ارسال SMS فعال', default=True)
    otp_enabled = models.BooleanField('OTP فعال', default=True)
    otp_for_sensitive = models.BooleanField('OTP برای عملیات حساس', default=False)
    otp_expiry_seconds = models.IntegerField('مدت اعتبار OTP (ثانیه)', default=120)
    otp_max_attempts = models.IntegerField('حداکثر تلاش OTP', default=3)
    otp_resend_cooldown = models.IntegerField('فاصله ارسال مجدد OTP (ثانیه)', default=120)

    # ── اعلان سفارش ─────────────────────────────────
    order_sms_enabled = models.BooleanField('ارسال پیامک پس از خرید', default=False,
                                             help_text='در صورت فعال بودن، پس از پرداخت موفق پیامک ارسال می‌شود')
    order_sms_text = models.TextField('متن پیامک سفارش', blank=True,
                                       default='سفارش شما با کد {order_number} با موفقیت ثبت شد. با تشکر از خرید شما.',
                                       help_text='از {order_number} برای درج شماره سفارش استفاده کنید')
    order_email_intro = models.TextField('متن مقدمه ایمیل سفارش', blank=True,
                                          default='با تشکر از خرید شما! سفارش شما با موفقیت ثبت و پرداخت شد.',
                                          help_text='متن بالای فاکتور در ایمیل')
    order_email_footer = models.TextField('متن پایانی ایمیل سفارش', blank=True,
                                           default='در صورت هرگونه سوال، با پشتیبانی ما در تماس باشید.',
                                           help_text='متن زیر فاکتور در ایمیل')

    # ── درگاه پرداخت ──────────────────────────────
    payment_gateway = models.CharField('درگاه پرداخت', max_length=50, blank=True, default='zarinpal')

    # ── پشتیبانی ───────────────────────────────────
    chat_mode = models.CharField('حالت چت', max_length=10,
                                 choices=(('ws', 'WebSocket'), ('poll', 'Polling')), default='poll')
    support_email_notifications_enabled = models.BooleanField('اعلان ایمیلی پشتیبانی', default=False)
    support_notify_email = models.CharField('ایمیل اعلان پشتیبانی', max_length=255, blank=True, default='')

    # ── تلگرام ─────────────────────────────────────
    telegram_admin_url = models.CharField('لینک تلگرام ادمین', max_length=255, blank=True,
                                          default='https://t.me/accountinox_admin')
    telegram_channel_url = models.CharField('لینک کانال تلگرام', max_length=255, blank=True,
                                            default='https://t.me/accountinox')
    telegram_support_label = models.CharField('برچسب پشتیبانی تلگرام', max_length=100, blank=True,
                                              default='پشتیبانی در تلگرام')

    # ── اطلاعات تماس ──────────────────────────────
    phone = models.CharField('شماره تماس', max_length=32, blank=True, default='')
    email = models.EmailField('ایمیل', blank=True, default='')
    instagram_url = models.CharField('لینک اینستاگرام', max_length=300, blank=True, default='')

    # ── متن قوانین و حریم خصوصی (قابل ویرایش از پنل ادمین) ──────────────
    terms_html = models.TextField('متن شرایط و قوانین (HTML)', blank=True, default='',
                                  help_text='متن شرایط و قوانین سایت — HTML مجاز است')
    privacy_html = models.TextField('متن سیاست حریم خصوصی (HTML)', blank=True, default='',
                                    help_text='متن سیاست حریم خصوصی — HTML مجاز است')
    # Timestamps for tracking when these pages were last edited in admin
    terms_updated = models.DateTimeField('تاریخ به‌روزرسانی شرایط', null=True, blank=True)
    privacy_updated = models.DateTimeField('تاریخ به‌روزرسانی حریم خصوصی', null=True, blank=True)

    # Site-wide top notice banner
    site_notice_enabled = models.BooleanField(
        'فعال‌سازی اطلاعیه سراسری',
        default=False,
        help_text='در صورت فعال بودن، نوار اطلاعیه در تمام صفحات سایت نمایش داده می‌شود.'
    )
    site_notice_text = models.CharField(
        'متن اطلاعیه سراسری',
        max_length=300,
        blank=True,
        default='',
        help_text='متنی که در نوار قرمز بالای سایت نمایش داده می‌شود.'
    )

    def __str__(self):
        return f"تنظیمات سایت ({self.site_name})"

    def save(self, *args, **kwargs):
        # Ensure singleton PK
        self.pk = 1

        # If object exists, detect changes to terms_html / privacy_html and update timestamps
        try:
            old = SiteSettings.objects.get(pk=1)
        except SiteSettings.DoesNotExist:
            old = None

        from django.utils import timezone
        now = timezone.now()
        if old is None:
            # fresh create — set timestamps if content present
            if self.terms_html:
                self.terms_updated = now
            if self.privacy_html:
                self.privacy_updated = now
        else:
            if self.terms_html and (old.terms_html != self.terms_html):
                self.terms_updated = now
            if self.privacy_html and (old.privacy_html != self.privacy_html):
                self.privacy_updated = now

        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1, defaults={
            'site_name': 'Accountinox',
            'brand_wordmark_fa': 'اکانتینوکس',
            'primary_color': '#1ABBC8',
            'secondary_color': '#0468BD',
            'accent_color': '#45E2CC',
            'telegram_admin_url': 'https://t.me/accountinox_admin',
            'telegram_channel_url': 'https://t.me/accountinox',
            'telegram_support_label': 'پشتیبانی در تلگرام',
        })
        return obj

    @classmethod
    def get_solo(cls):
        obj = cls.objects.first()
        if not obj:
            obj = cls.objects.create()
        return obj

    class Meta:
        verbose_name = 'تنظیمات سایت'
        verbose_name_plural = 'تنظیمات سایت'


class SiteBackup(models.Model):
    file_name = models.CharField('نام فایل بکاپ', max_length=255, unique=True)
    size_bytes = models.BigIntegerField('حجم بکاپ (بایت)', default=0)
    created_at = models.DateTimeField('تاریخ ساخت', auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='ایجاد شده توسط',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='site_backups',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'بکاپ سایت'
        verbose_name_plural = 'بکاپ‌های سایت'

    def __str__(self):
        return self.file_name

    @staticmethod
    def backup_directory() -> Path:
        backup_dir = Path(settings.BASE_DIR) / 'backups' / 'site'
        backup_dir.mkdir(parents=True, exist_ok=True)
        return backup_dir

    @property
    def file_path(self) -> Path:
        return self.backup_directory() / self.file_name

    @property
    def file_exists(self) -> bool:
        return self.file_path.exists()

    def delete(self, *args, **kwargs):
        path = self.file_path
        super().delete(*args, **kwargs)
        if path.exists():
            path.unlink()


class HeroBanner(models.Model):
    """Slider banners displayed on the landing page — fully managed from admin."""

    BADGE_COLOR_CHOICES = [
        ('primary', 'سبز (Primary)'),
        ('amber', 'زرد / نارنجی (Amber)'),
        ('emerald', 'سبز روشن (Emerald)'),
        ('sky', 'آبی (Sky)'),
        ('red', 'قرمز (Red)'),
        ('violet', 'بنفش (Violet)'),
    ]

    title = models.CharField('عنوان اصلی', max_length=120,
                             help_text='خط اول عنوان بنر — مثلاً «اکانت‌های پریمیوم»')
    title_highlight = models.CharField('عنوان رنگی (گرادیان)', max_length=120, blank=True,
                                       help_text='خط دوم عنوان که با رنگ گرادیان نمایش داده می‌شود — مثلاً «با تضمین کیفیت»')
    description = models.TextField('توضیحات', max_length=300, blank=True,
                                   help_text='متن زیر عنوان — حداکثر ۳۰۰ کاراکتر')

    # Badge / label
    badge_text = models.CharField('متن بج', max_length=80, blank=True,
                                  help_text='متن کنار آیکون بالای عنوان — مثلاً «تحویل فوری · پشتیبانی ۲۴ ساعته»')
    badge_color = models.CharField('رنگ بج', max_length=20, choices=BADGE_COLOR_CHOICES, default='primary')

    # Buttons
    button_text = models.CharField('متن دکمه اصلی', max_length=60, blank=True, default='مشاهده محصولات')
    button_url = models.CharField('لینک دکمه اصلی', max_length=300, blank=True, default='/shop/')
    button2_text = models.CharField('متن دکمه دوم', max_length=60, blank=True,
                                    help_text='اختیاری — خالی بگذارید اگر فقط یک دکمه می‌خواهید')
    button2_url = models.CharField('لینک دکمه دوم', max_length=300, blank=True)

    # Background
    background_image = models.ImageField('تصویر پس‌زمینه', upload_to='banners/', blank=True, null=True,
                                         help_text='اختیاری — در صورت آپلود، جایگزین گرادیان پیش‌فرض می‌شود')

    # Status & ordering
    is_active = models.BooleanField('فعال', default=True)
    order = models.PositiveIntegerField('ترتیب نمایش', default=0,
                                        help_text='عدد کوچک‌تر = نمایش زودتر')
    created_at = models.DateTimeField('تاریخ ایجاد', auto_now_add=True)
    updated_at = models.DateTimeField('آخرین ویرایش', auto_now=True)

    class Meta:
        ordering = ['order', '-created_at']
        verbose_name = 'بنر اسلایدر'
        verbose_name_plural = 'بنرهای اسلایدر'

    def __str__(self):
        status = '✅' if self.is_active else '❌'
        return f'{status} {self.title}'


class GlobalFAQ(models.Model):
    question = models.CharField('سوال', max_length=255)
    answer = models.TextField('پاسخ')
    ordering = models.IntegerField('ترتیب', default=0)

    class Meta:
        ordering = ['ordering']
        verbose_name = 'سوال متداول'
        verbose_name_plural = 'سوالات متداول'

    def __str__(self):
        return self.question


class TrustStat(models.Model):
    """آمار اعتمادسازی — نوار بالای صفحه اصلی (مثلاً «+۱۰,۰۰۰ مشتری راضی»)"""
    ICON_CHOICES = [
        ('users', 'کاربران'),
        ('headset', 'پشتیبانی'),
        ('shield', 'امنیت'),
        ('star', 'ستاره'),
        ('check', 'تیک'),
        ('clock', 'ساعت'),
        ('truck', 'ارسال'),
        ('heart', 'قلب'),
    ]

    icon = models.CharField('آیکون', max_length=30, choices=ICON_CHOICES, default='check')
    value = models.CharField('مقدار', max_length=40,
                             help_text='مثلاً «+۱۰,۰۰۰» یا «۲۴/۷» یا «۱۰۰٪»')
    label = models.CharField('برچسب', max_length=80,
                             help_text='مثلاً «مشتری راضی» یا «پشتیبانی آنلاین»')
    order = models.PositiveIntegerField('ترتیب', default=0)
    is_active = models.BooleanField('فعال', default=True)

    class Meta:
        ordering = ['order']
        verbose_name = 'آمار اعتماد'
        verbose_name_plural = 'آمارهای اعتماد'

    def __str__(self):
        return f'{self.value} {self.label}'


class FeatureCard(models.Model):
    """کارت ویژگی‌ها — بخش «چرا اکانتینوکس؟» صفحه اصلی"""
    ICON_CHOICES = [
        ('bolt', 'رعد و برق (تحویل آنی)'),
        ('shield', 'سپر (تضمین)'),
        ('headset', 'هدست (پشتیبانی)'),
        ('dollar', 'دلار (قیمت)'),
        ('star', 'ستاره'),
        ('lock', 'قفل (امنیت)'),
        ('rocket', 'موشک'),
        ('gift', 'هدیه'),
    ]

    icon = models.CharField('آیکون', max_length=30, choices=ICON_CHOICES, default='bolt')
    title = models.CharField('عنوان', max_length=100)
    description = models.TextField('توضیحات', max_length=300)
    order = models.PositiveIntegerField('ترتیب', default=0)
    is_active = models.BooleanField('فعال', default=True)

    class Meta:
        ordering = ['order']
        verbose_name = 'کارت ویژگی'
        verbose_name_plural = 'کارت‌های ویژگی'

    def __str__(self):
        return self.title


class FooterLink(models.Model):
    """لینک‌های فوتر — ستون‌ها و لینک‌های پایین صفحه"""
    COLUMN_CHOICES = [
        ('quick', 'دسترسی سریع'),
        ('legal', 'قوانین'),
    ]

    column = models.CharField('ستون', max_length=20, choices=COLUMN_CHOICES, default='quick')
    label = models.CharField('عنوان لینک', max_length=100)
    url = models.CharField('آدرس', max_length=300)
    order = models.PositiveIntegerField('ترتیب', default=0)
    is_active = models.BooleanField('فعال', default=True)
    open_new_tab = models.BooleanField('باز شدن در تب جدید', default=False)

    class Meta:
        ordering = ['column', 'order']
        verbose_name = 'لینک فوتر'
        verbose_name_plural = 'لینک‌های فوتر'

    def __str__(self):
        return f'{self.get_column_display()} → {self.label}'
