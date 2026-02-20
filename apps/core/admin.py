from django.conf import settings
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from .backup_utils import create_site_backup, import_site_backup, restore_site_backup
from .models import SiteSettings, SiteBackup, GlobalFAQ, HeroBanner, TrustStat, FeatureCard, FooterLink


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
        ('🚨 اطلاعیه سراسری سایت', {
            'fields': ('site_notice_enabled', 'site_notice_text'),
            'description': 'در صورت فعال بودن، نوار قرمز اطلاعیه در بالای تمام صفحات سایت نمایش داده می‌شود.',
        }),
        ('🔐 ورود با گوگل (Google OAuth)', {
            'fields': ('google_oauth_enabled', 'google_oauth_button_text', 'google_oauth_status', 'google_oauth_help'),
            'description': 'برای فعال‌سازی کامل، تنظیمات Google OAuth را طبق راهنما انجام دهید.',
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
        ('📦 اعلان سفارش', {
            'fields': (
                'order_sms_enabled',
                'order_sms_text',
                'order_email_intro',
                'order_email_footer',
                'vat_enabled',
                'vat_percent',
            ),
            'description': 'تنظیمات ایمیل/پیامک پس از خرید و مالیات فاکتور. در متن پیامک از {order_number} برای درج شماره سفارش استفاده کنید.',
        }),
        ('💳 درگاه پرداخت', {
            'fields': ('payment_gateway',),
            'classes': ('collapse',),
        }),
        ('💬 پشتیبانی', {
            'fields': (
                'chat_mode',
                'support_email_notifications_enabled',
                'support_notify_email',
                'support_sla_warning_seconds',
                'support_sla_breach_seconds',
            ),
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

    @admin.display(description='وضعیت اتصال گوگل')
    def google_oauth_status(self, obj):
        provider_cfg = getattr(settings, 'SOCIALACCOUNT_PROVIDERS', {}).get('google', {})
        app_cfg = provider_cfg.get('APP') or {}
        env_configured = bool(str(app_cfg.get('client_id', '')).strip() and str(app_cfg.get('secret', '')).strip())

        db_configured = False
        db_count = 0
        try:
            from allauth.socialaccount.models import SocialApp
            from django.contrib.sites.models import Site

            current_site = Site.objects.filter(id=settings.SITE_ID).first()
            apps_qs = SocialApp.objects.filter(provider='google')
            if current_site:
                apps_qs = apps_qs.filter(sites=current_site)
            db_count = apps_qs.count()
            db_configured = db_count > 0
        except Exception:
            db_configured = False

        if env_configured or db_configured:
            return format_html(
                '<span style="color:#0f766e;font-weight:600;">آماده</span> '
                '<small style="opacity:.8;">(env: {} | social app: {})</small>',
                'ok' if env_configured else 'off',
                db_count,
            )
        return format_html(
            '<span style="color:#b91c1c;font-weight:600;">ناقص</span> '
            '<small style="opacity:.8;">(کلیدهای گوگل یا Social App تنظیم نشده)</small>'
        )

    @admin.display(description='راهنمای تنظیم')
    def google_oauth_help(self, obj):
        base_url = (getattr(settings, 'SITE_BASE_URL', '') or getattr(settings, 'SITE_URL', '') or '').strip().rstrip('/')
        if not base_url:
            base_url = 'https://your-domain.com'
        callback_url = f'{base_url}/accounts/google/login/callback/'
        login_url = f'{base_url}/accounts/google/login/'
        return format_html(
            '<ol style="margin:0;padding-right:1.2rem;">'
            '<li>در Google Cloud یک OAuth Client از نوع <strong>Web application</strong> بسازید.</li>'
            '<li>این Callback را در Authorized redirect URIs بگذارید: <code>{}</code></li>'
            '<li>یکی از دو روش را کامل کنید: '
            'الف) وارد کردن <code>GOOGLE_CLIENT_ID</code> و <code>GOOGLE_SECRET</code> در .env '
            'یا ب) ساخت SocialApp برای provider=google در ادمین.</li>'
            '<li>تست ورود: <a href="{}" target="_blank" rel="noopener">{}</a></li>'
            '</ol>',
            callback_url,
            login_url,
            login_url,
        )

    readonly_fields = ('terms_updated', 'privacy_updated', 'google_oauth_status', 'google_oauth_help')


@admin.register(SiteBackup)
class SiteBackupAdmin(admin.ModelAdmin):
    list_display = (
        'file_name',
        'created_at',
        'created_by',
        'size_pretty',
        'download_link',
        'restore_link',
        'archive_status',
    )
    search_fields = ('file_name', 'created_by__username', 'created_by__email')
    ordering = ('-created_at',)
    readonly_fields = ('file_name', 'size_bytes', 'created_at', 'created_by', 'size_pretty', 'archive_status')
    actions = ('restore_selected',)

    def has_module_permission(self, request):
        return _is_owner(request.user)

    def has_view_permission(self, request, obj=None):
        return _is_owner(request.user)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return _is_owner(request.user)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'create-backup/',
                self.admin_site.admin_view(self.create_backup_view),
                name='core_sitebackup_create',
            ),
            path(
                'import-backup/',
                self.admin_site.admin_view(self.import_backup_view),
                name='core_sitebackup_import',
            ),
            path(
                '<int:backup_id>/download/',
                self.admin_site.admin_view(self.download_backup_view),
                name='core_sitebackup_download',
            ),
            path(
                '<int:backup_id>/restore/',
                self.admin_site.admin_view(self.restore_backup_view),
                name='core_sitebackup_restore',
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['can_create_backup'] = _is_owner(request.user)
        extra_context['can_import_backup'] = _is_owner(request.user)
        return super().changelist_view(request, extra_context=extra_context)

    @admin.display(description='حجم')
    def size_pretty(self, obj):
        size = int(obj.size_bytes or 0)
        units = ('B', 'KB', 'MB', 'GB', 'TB')
        index = 0
        value = float(size)
        while value >= 1024 and index < len(units) - 1:
            value /= 1024
            index += 1
        if index == 0:
            return f'{int(value)} {units[index]}'
        return f'{value:.2f} {units[index]}'

    @admin.display(description='وضعیت فایل')
    def archive_status(self, obj):
        if obj.file_exists:
            return format_html('<span style="color:#0f766e;font-weight:600;">موجود</span>')
        return format_html('<span style="color:#b91c1c;font-weight:600;">مفقود</span>')

    @admin.display(description='دانلود')
    def download_link(self, obj):
        if not obj.file_exists:
            return '-'
        url = reverse('admin:core_sitebackup_download', args=(obj.pk,))
        return format_html('<a class="button" href="{}">دانلود</a>', url)

    @admin.display(description='ریستور')
    def restore_link(self, obj):
        if not obj.file_exists:
            return '-'
        url = reverse('admin:core_sitebackup_restore', args=(obj.pk,))
        return format_html(
            '<a class="button" style="background:#b91c1c;border-color:#b91c1c;color:#fff;" href="{}">ریستور</a>',
            url,
        )

    @admin.action(description='ریستور بکاپ انتخاب‌شده')
    def restore_selected(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, 'برای ریستور باید دقیقا یک بکاپ انتخاب شود.', level=messages.ERROR)
            return
        selected = queryset.first()
        url = reverse('admin:core_sitebackup_restore', args=(selected.pk,))
        return HttpResponseRedirect(url)

    def delete_model(self, request, obj):
        obj.delete()

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            obj.delete()

    def _get_backup_object(self, backup_id):
        try:
            return SiteBackup.objects.get(pk=backup_id)
        except SiteBackup.DoesNotExist as exc:
            raise Http404('بکاپ پیدا نشد') from exc

    def create_backup_view(self, request):
        if not _is_owner(request.user):
            raise PermissionDenied
        try:
            backup = create_site_backup(user=request.user)
            self.message_user(
                request,
                f'بکاپ با موفقیت ساخته شد: {backup.file_name}',
                level=messages.SUCCESS,
            )
        except Exception as exc:
            self.message_user(request, f'ساخت بکاپ ناموفق بود: {exc}', level=messages.ERROR)
        return HttpResponseRedirect(reverse('admin:core_sitebackup_changelist'))

    def import_backup_view(self, request):
        if not _is_owner(request.user):
            raise PermissionDenied

        if request.method == 'POST':
            upload = request.FILES.get('backup_file')
            if upload is None:
                self.message_user(request, 'هیچ فایلی انتخاب نشده است.', level=messages.ERROR)
                return HttpResponseRedirect(reverse('admin:core_sitebackup_import'))
            try:
                backup = import_site_backup(upload, user=request.user)
                self.message_user(request, f'بکاپ با موفقیت ایمپورت شد: {backup.file_name}', level=messages.SUCCESS)
                return HttpResponseRedirect(reverse('admin:core_sitebackup_changelist'))
            except Exception as exc:
                self.message_user(request, f'ایمپورت بکاپ ناموفق بود: {exc}', level=messages.ERROR)
                return HttpResponseRedirect(reverse('admin:core_sitebackup_import'))

        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'title': 'ایمپورت بکاپ',
        }
        return TemplateResponse(request, 'admin/core/sitebackup/import_form.html', context)

    def download_backup_view(self, request, backup_id):
        if not _is_owner(request.user):
            raise PermissionDenied
        backup = self._get_backup_object(backup_id)
        if not backup.file_exists:
            raise Http404('فایل بکاپ پیدا نشد')
        return FileResponse(
            backup.file_path.open('rb'),
            as_attachment=True,
            filename=backup.file_name,
        )

    def restore_backup_view(self, request, backup_id):
        if not _is_owner(request.user):
            raise PermissionDenied
        backup = self._get_backup_object(backup_id)
        if not backup.file_exists:
            self.message_user(request, 'فایل بکاپ موجود نیست.', level=messages.ERROR)
            return HttpResponseRedirect(reverse('admin:core_sitebackup_changelist'))

        if request.method == 'POST':
            try:
                restore_site_backup(backup)
                self.message_user(
                    request,
                    'ریستور بکاپ با موفقیت انجام شد. ممکن است لازم باشد دوباره وارد پنل شوید.',
                    level=messages.SUCCESS,
                )
            except Exception as exc:
                self.message_user(request, f'ریستور ناموفق بود: {exc}', level=messages.ERROR)
            return HttpResponseRedirect(reverse('admin:core_sitebackup_changelist'))

        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'backup': backup,
            'title': f'تایید ریستور: {backup.file_name}',
        }
        return TemplateResponse(request, 'admin/core/sitebackup/restore_confirm.html', context)


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
