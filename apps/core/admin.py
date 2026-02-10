from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from .models import SiteSettings, GlobalFAQ


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ('site_name', 'brand_wordmark_fa', 'tailwind_mode', 'payment_gateway', 'sms_provider')
    fieldsets = (
        ('عمومی', {'fields': ('site_name', 'brand_wordmark_fa', 'logo')}),
        ('رنگ‌ها و ظاهری', {'fields': ('primary_color', 'secondary_color', 'accent_color', 'tailwind_mode')}),
        ('OTP / SMS', {'fields': ('otp_enabled', 'otp_for_sensitive', 'otp_expiry_seconds', 'otp_max_attempts', 'otp_resend_cooldown', 'sms_provider', 'sms_enabled')}),
        ('درگاه پرداخت', {'fields': ('payment_gateway',)}),
        ('پشتیبانی / اینماد', {'fields': ('chat_mode', 'enamad_html')}),
    )

    def has_add_permission(self, request):
        # disallow adding more than one instance
        return not SiteSettings.objects.exists()

    def changelist_view(self, request, extra_context=None):
        """Redirect the changelist to the single instance change page."""
        obj = SiteSettings.load()
        url = reverse('admin:%s_%s_change' % (obj._meta.app_label, obj._meta.model_name), args=(obj.pk,))
        return HttpResponseRedirect(url)


@admin.register(GlobalFAQ)
class GlobalFAQAdmin(admin.ModelAdmin):
    list_display = ('question', 'ordering')

