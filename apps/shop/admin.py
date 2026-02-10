from django.contrib import admin
from django.db.models import Exists, OuterRef
from django.urls import reverse
from django.utils.html import format_html

from .models import AccountItem, Category, Order, OrderItem, Product, TransactionLog


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name', 'slug')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'price', 'slug', 'thumbnail_preview')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('thumbnail_preview',)
    list_filter = ('category',)
    search_fields = ('title', 'slug', 'description', 'seo_title')
    fieldsets = (
        ('عمومی', {'fields': ('title', 'slug', 'category', 'description')}),
        ('تصویر', {'fields': ('featured_image', 'thumbnail_preview')}),
        ('قیمت', {'fields': ('price',)}),
        ('SEO', {'fields': ('seo_title', 'seo_description')}),
    )

    def thumbnail_preview(self, obj):
        if obj.featured_image:
            return format_html(
                '<img src="{}" style="max-width: 200px; max-height: 200px;" />',
                obj.featured_image.url,
            )
        return '(بدون تصویر)'
    
    @admin.display(description='پیش‌نمایش تصویر')
    def thumbnail_preview_display(self, obj):
        return self.thumbnail_preview(obj)


@admin.register(AccountItem)
class AccountItemAdmin(admin.ModelAdmin):
    list_display = ('product', 'allocated', 'created_at')
    list_filter = ('allocated', 'created_at')
    search_fields = ('product__title',)
    readonly_fields = ('username_encrypted', 'password_encrypted', 'notes_encrypted')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    class FailedPaymentFilter(admin.SimpleListFilter):
        title = 'تراکنش ناموفق'
        parameter_name = 'failed_payment'

        def lookups(self, request, model_admin):
            return (
                ('yes', 'دارد'),
                ('no', 'ندارد'),
            )

        def queryset(self, request, queryset):
            value = self.value()
            if value == 'yes':
                return queryset.filter(failed_payment_exists=True)
            if value == 'no':
                return queryset.filter(failed_payment_exists=False)
            return queryset

    list_display = (
        'id',
        'user',
        'total',
        'order_status_badge',
        'payment_status_badge',
        'related_transactions_link',
        'created_at',
    )
    list_filter = ('status', 'paid', 'created_at', FailedPaymentFilter)
    search_fields = (
        'id',
        'user__username',
        'user__email',
        'customer_name',
        'customer_phone',
        'customer_email',
    )
    list_select_related = ('user',)
    date_hierarchy = 'created_at'
    fieldsets = (
        ('وضعیت سفارش', {'fields': ('status', 'paid', 'status_updated_at')}),
        ('اطلاعات مشتری', {'fields': ('user', 'customer_name', 'customer_phone', 'customer_email')}),
        ('آدرس تحویل', {'fields': ('shipping_address',)}),
        ('جزئیات مالی', {'fields': ('total', 'created_at')}),
    )
    readonly_fields = ('created_at', 'status_updated_at')

    def get_queryset(self, request):
        failed_tx = TransactionLog.objects.filter(order=OuterRef('pk'), success=False)
        return super().get_queryset(request).annotate(failed_payment_exists=Exists(failed_tx))

    @admin.display(description='وضعیت سفارش', ordering='status')
    def order_status_badge(self, obj):
        status_class_map = {
            Order.STATUS_PENDING_REVIEW: 'status-badge--warning',
            Order.STATUS_CONFIRMED: 'status-badge--success',
            Order.STATUS_DELIVERED: 'status-badge--success',
            Order.STATUS_CANCELLED: 'status-badge--danger',
        }
        css_class = status_class_map.get(obj.status, 'status-badge--muted')
        return format_html(
            '<span class="status-badge {}">{}</span>',
            css_class,
            obj.get_status_display(),
        )

    @admin.display(description='وضعیت پرداخت', ordering='paid')
    def payment_status_badge(self, obj):
        if obj.paid:
            return format_html('<span class="status-badge status-badge--success">{}</span>', 'پرداخت‌شده')
        if getattr(obj, 'failed_payment_exists', False):
            return format_html('<span class="status-badge status-badge--danger">{}</span>', 'پرداخت ناموفق')
        return format_html('<span class="status-badge status-badge--warning">{}</span>', 'در انتظار')

    @admin.display(description='تراکنش‌ها')
    def related_transactions_link(self, obj):
        if not obj.pk:
            return '-'
        url = f'{reverse("admin:shop_transactionlog_changelist")}?order__id__exact={obj.pk}'
        return format_html('<a class="admin-row-action" href="{}">مشاهده تراکنش‌ها</a>', url)


@admin.register(TransactionLog)
class TransactionLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'provider', 'success_status', 'created_at')
    list_filter = ('provider', 'success', 'created_at')
    search_fields = ('id', 'provider', 'order__id')
    list_select_related = ('order',)

    @admin.display(description='نتیجه', ordering='success')
    def success_status(self, obj):
        if obj.success:
            return format_html('<span class="status-badge status-badge--success">{}</span>', 'موفق')
        return format_html('<span class="status-badge status-badge--danger">{}</span>', 'ناموفق')

