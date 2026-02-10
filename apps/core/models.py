from django.db import models


class SiteSettings(models.Model):
    site_name = models.CharField(max_length=150, default='Accountinox')
    brand_wordmark_fa = models.CharField(max_length=150, blank=True, default='اکانتینوکس')
    logo = models.ImageField(upload_to='logos/', blank=True, null=True)
    primary_color = models.CharField(max_length=7, default='#1ABBC8')
    secondary_color = models.CharField(max_length=7, default='#0468BD')
    accent_color = models.CharField(max_length=7, default='#45E2CC')
    tailwind_mode = models.CharField(max_length=10, choices=(('cdn','cdn'),('local','local')), default='cdn')
    enamad_html = models.TextField(blank=True, default='')
    sms_provider = models.CharField(max_length=100, blank=True, default='console')
    sms_enabled = models.BooleanField(default=True)
    otp_enabled = models.BooleanField(default=True)
    otp_for_sensitive = models.BooleanField(default=False)
    otp_expiry_seconds = models.IntegerField(default=300)
    otp_max_attempts = models.IntegerField(default=5)
    otp_resend_cooldown = models.IntegerField(default=60)
    payment_gateway = models.CharField(max_length=50, blank=True, default='zarinpal')
    chat_mode = models.CharField(max_length=10, choices=(('ws','ws'),('poll','poll')), default='poll')
    # Support notifications
    support_email_notifications_enabled = models.BooleanField(default=False)
    support_notify_email = models.CharField(max_length=255, blank=True, default='')
    # Telegram links for support/admin
    telegram_admin_url = models.CharField(max_length=255, blank=True, default='https://t.me/accountinox_admin')
    telegram_channel_url = models.CharField(max_length=255, blank=True, default='https://t.me/accountinox')
    telegram_support_label = models.CharField(max_length=100, blank=True, default='پشتیبانی در تلگرام')

    def __str__(self):
        return f"SiteSettings ({self.site_name})"

    def save(self, *args, **kwargs):
        """
        Enforce singleton: always use PK=1 and ensure only one instance.
        """
        self.pk = 1
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
        """Return the single SiteSettings instance, creating it if necessary."""
        obj = cls.objects.first()
        if not obj:
            obj = cls.objects.create()
        return obj

    class Meta:
        verbose_name = 'Site Settings'
        verbose_name_plural = 'Site Settings'


class GlobalFAQ(models.Model):
    question = models.CharField(max_length=255)
    answer = models.TextField()
    ordering = models.IntegerField(default=0)

    class Meta:
        ordering = ['ordering']

    def __str__(self):
        return self.question
