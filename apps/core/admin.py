from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from .models import SiteSettings, GlobalFAQ, HeroBanner, TrustStat, FeatureCard, FooterLink


def _is_owner(user):
    """Check if user is superuser or in Owner group — used to restrict site-level settings."""
    return bool(
        user and user.is_authenticated
        and (user.is_superuser or user.groups.filter(name='Owner').exists())
    )


class OwnerOnlyMixin:
    """Restrict add/change/delete/view to owner/superuser. Regular staff can only view."""

    def has_module_permission(self, request):
        return request.user.is_staff

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    def has_add_permission(self, request):
        return _is_owner(request.user)

    def has_change_permission(self, request, obj=None):
        return _is_owner(request.user)

    def has_delete_permission(self, request, obj=None):
        return _is_owner(request.user)


# ── بنرهای اسلایدر ─────────────────────────────────

@admin.register(HeroBanner)
class HeroBannerAdmin(admin.ModelAdmin):
    list_display = ('title', 'badge_text', 'badge_color', 'is_active', 'order', 'bg_preview', 'updated_at')
    list_editable = ('is_active', 'order')
    list_filter = ('is_active', 'badge_color')
    search_fields = ('title', 'title_highlight', 'description')
    readonly_fields = ('created_at', 'updated_at', 'bg_preview_large')
    fieldsets = (
        ('محتوای بنر', {
            'fields': ('title', 'title_highlight', 'description'),
        }),
        ('بج / برچسب', {
            'fields': ('badge_text', 'badge_color'),
        }),
        ('دکمه‌ها', {
            'fields': ('button_text', 'button_url', 'button2_text', 'button2_url'),
        }),
        ('تصویر پس‌زمینه', {
            'fields': ('background_image', 'bg_preview_large'),
            'description': 'اختیاری — اگر تصویری آپلود شود بجای گرادیان پیش‌فرض نمایش داده می‌شود.',
        }),
        ('وضعیت', {
            'fields': ('is_active', 'order'),
        }),
        ('تاریخ‌ها', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='پیش‌نمایش')
    def bg_preview(self, obj):
        if obj.background_image:
            return format_html(
                '<img src="{}" style="width:60px;height:36px;object-fit:cover;border-radius:4px;" />',
                obj.background_image.url)
        return '—'

    @admin.display(description='پیش‌نمایش تصویر')
    def bg_preview_large(self, obj):
        if obj.background_image:
            return format_html(
                '<img src="{}" style="max-width:400px;max-height:200px;border-radius:8px;" />',
                obj.background_image.url)
        return '(بدون تصویر)'


# ── تنظیمات سایت (Singleton) ───────────────────────

@admin.register(SiteSettings)
class SiteSettingsAdmin(OwnerOnlyMixin, admin.ModelAdmin):
    list_display = ('site_name', 'brand_wordmark_fa', 'payment_gateway', 'sms_provider')
    fieldsets = (
        ('🏢 اطلاعات سایت', {
            'fields': ('site_name', 'brand_wordmark_fa', 'logo', 'site_description'),
        }),
        ('🎨 رنگ‌ها و ظاهر', {
            'fields': ('primary_color', 'secondary_color', 'accent_color', 'tailwind_mode'),
            'classes': ('collapse',),
        }),
        ('📱 اطلاعات تماس', {
            'fields': ('phone', 'email', 'instagram_url'),
        }),
        ('📣 تلگرام', {
            'fields': ('telegram_admin_url', 'telegram_channel_url', 'telegram_support_label'),
        }),
        ('🏠 عناوین صفحه اصلی', {
            'fields': ('features_title', 'features_subtitle', 'products_title', 'products_subtitle'),
            'description': 'عناوین بخش‌های مختلف صفحه اصلی لندینگ',
        }),
        ('📢 بخش CTA (فراخوانی)', {
            'fields': ('cta_title', 'cta_description', 'cta_button1_text', 'cta_button1_url',
                       'cta_button2_text', 'cta_button2_url'),
        }),
        ('🔗 فوتر', {
            'fields': ('footer_copyright', 'footer_developer_name', 'footer_developer_url'),
        }),
        ('🔐 OTP / SMS', {
            'fields': ('otp_enabled', 'otp_for_sensitive', 'otp_expiry_seconds',
                       'otp_max_attempts', 'otp_resend_cooldown', 'sms_provider', 'sms_enabled'),
            'classes': ('collapse',),
        }),
        ('� اعلان سفارش', {
            'fields': ('order_sms_enabled', 'order_sms_text', 'order_email_intro', 'order_email_footer'),
            'description': 'تنظیمات ایمیل و پیامک پس از خرید موفق. در متن پیامک از {order_number} برای درج شماره سفارش استفاده کنید.',
        }),
        ('�💳 درگاه پرداخت', {
            'fields': ('payment_gateway',),
            'classes': ('collapse',),
        }),
        ('💬 پشتیبانی', {
            'fields': ('chat_mode', 'support_email_notifications_enabled', 'support_notify_email'),
            'classes': ('collapse',),
        }),
        ('✅ اینماد و نمادها', {
            'fields': ('enamad_html',),
            'classes': ('collapse',),
        }),
        ('📜 قوانین و حریم خصوصی', {
            'fields': ('terms_html', 'privacy_html'),
            'description': 'متن کامل صفحات «شرایط استفاده» و «حریم خصوصی». می‌توانید HTML ساده وارد کنید.',
        }),
        ('🕒 تاریخ‌های ویرایش', {
            'fields': ('terms_updated', 'privacy_updated'),
            'classes': ('collapse',),
        }),
    )

    def has_add_permission(self, request):
        # Singleton: block add if already exists, AND require owner
        if not _is_owner(request.user):
            return False
        return not SiteSettings.objects.exists()

    def changelist_view(self, request, extra_context=None):
        obj = SiteSettings.load()
        url = reverse('admin:%s_%s_change' % (obj._meta.app_label, obj._meta.model_name), args=(obj.pk,))
        return HttpResponseRedirect(url)

    readonly_fields = ('terms_updated', 'privacy_updated')


# ── سوالات متداول ───────────────────────────────────

@admin.register(GlobalFAQ)
class GlobalFAQAdmin(admin.ModelAdmin):
    list_display = ('question', 'short_answer', 'ordering')
    list_editable = ('ordering',)
    search_fields = ('question', 'answer')

    @admin.display(description='پاسخ (خلاصه)')
    def short_answer(self, obj):
        return obj.answer[:80] + '…' if len(obj.answer) > 80 else obj.answer


# ── آمار اعتماد (Trust Stats) ──────────────────────

@admin.register(TrustStat)
class TrustStatAdmin(admin.ModelAdmin):
    list_display = ('icon', 'value', 'label', 'order', 'is_active')
    list_editable = ('order', 'is_active')
    list_filter = ('is_active',)


# ── کارت ویژگی‌ها (Feature Cards) ──────────────────

@admin.register(FeatureCard)
class FeatureCardAdmin(admin.ModelAdmin):
    list_display = ('icon', 'title', 'short_desc', 'order', 'is_active')
    list_editable = ('order', 'is_active')
    list_filter = ('is_active',)

    @admin.display(description='توضیحات')
    def short_desc(self, obj):
        return obj.description[:60] + '…' if len(obj.description) > 60 else obj.description


# ── لینک‌های فوتر ───────────────────────────────────

@admin.register(FooterLink)
class FooterLinkAdmin(admin.ModelAdmin):
    list_display = ('label', 'column', 'url', 'order', 'is_active', 'open_new_tab')
    list_editable = ('order', 'is_active', 'open_new_tab')
    list_filter = ('column', 'is_active')
    search_fields = ('label', 'url')

