from django.contrib import admin

from .models import OrderAddress, PhoneOTP, Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone')
    search_fields = ('user__username', 'user__email', 'phone')


@admin.register(PhoneOTP)
class PhoneOTPAdmin(admin.ModelAdmin):
    list_display = ('phone', 'created_at', 'last_sent_at', 'attempts', 'locked_until')
    search_fields = ('phone',)


@admin.register(OrderAddress)
class OrderAddressAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'full_name',
        'phone',
        'city',
        'province',
        'is_default',
        'updated_at',
    )
    list_filter = ('is_default', 'province', 'city')
    search_fields = ('full_name', 'phone', 'user__username', 'user__email', 'city', 'province')
