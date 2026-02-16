from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone

from .models import OrderAddress, PhoneOTP, Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'user_email', 'phone', 'user_joined')
    search_fields = ('user__username', 'user__email', 'phone')
    list_select_related = ('user',)
    raw_id_fields = ('user',)

    @admin.display(description='ایمیل', ordering='user__email')
    def user_email(self, obj):
        return obj.user.email or '–'

    @admin.display(description='تاریخ عضویت', ordering='user__date_joined')
    def user_joined(self, obj):
        return obj.user.date_joined.strftime('%Y/%m/%d')


@admin.register(PhoneOTP)
class PhoneOTPAdmin(admin.ModelAdmin):
    list_display = ('phone', 'otp_status', 'attempts', 'created_at', 'last_sent_at', 'locked_until')
    search_fields = ('phone',)
    list_filter = ('created_at',)
    readonly_fields = ('phone', 'otp_hmac', 'created_at', 'last_sent_at', 'attempts', 'locked_until')

    @admin.display(description='وضعیت')
    def otp_status(self, obj):
        if obj.locked_until and obj.locked_until > timezone.now():
            return format_html('<span class="status-badge status-badge--danger">{}</span>', 'قفل شده')
        if obj.is_expired(300):
            return format_html('<span class="status-badge status-badge--muted">{}</span>', 'منقضی')
        return format_html('<span class="status-badge status-badge--success">{}</span>', 'فعال')


@admin.register(OrderAddress)
class OrderAddressAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'full_name',
        'phone',
        'city',
        'province',
        'default_badge',
        'updated_at',
    )
    list_filter = ('is_default', 'province', 'city')
    search_fields = ('full_name', 'phone', 'user__username', 'user__email', 'city', 'province')
    list_select_related = ('user',)
    fieldsets = (
        ('کاربر', {'fields': ('user',)}),
        ('اطلاعات آدرس', {
            'fields': ('label', 'full_name', 'phone', 'province', 'city', 'street_address', 'postal_code'),
        }),
        ('وضعیت', {'fields': ('is_default',)}),
    )

    @admin.display(description='پیش‌فرض', ordering='is_default')
    def default_badge(self, obj):
        if obj.is_default:
            return format_html('<span class="status-badge status-badge--success">{}</span>', 'پیش‌فرض')
        return '–'
