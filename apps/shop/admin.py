from django.contrib import admin
from django.db.models import Exists, OuterRef, Count
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import AccountItem, Category, Order, OrderItem, Product, ProductVariant, ProductRegion, TransactionLog, Service


# ── دسته‌بندی ───────────────────────────────────────

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'products_count')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_products_count=Count('product'))

    @admin.display(description='تعداد خدمت', ordering='_products_count')
    def products_count(self, obj):
        return obj._products_count


# ── خدمت (مرکز اصلی مدیریت) ────────────────────────

class ProductRegionInline(admin.TabularInline):
    model = ProductRegion
    fields = ('name', 'sort_order', 'is_active')
    extra = 1
    verbose_name = 'ریجن'
    verbose_name_plural = '۱. ریجن‌ها (ابتدا ریجن‌ها را تعریف و ذخیره کنید، سپس تنوع قیمتی بسازید)'


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    fields = ('region', 'name', 'price', 'sort_order', 'is_active')
    extra = 1
    verbose_name = 'تنوع قیمتی'
    verbose_name_plural = '۲. تنوع‌های قیمتی (پلن‌های قیمتی — هر ریجن پلن‌های خودش را دارد)'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'region':
            parent_id = request.resolver_match.kwargs.get('object_id')
            if parent_id:
                kwargs['queryset'] = ProductRegion.objects.filter(product_id=parent_id)
            else:
                kwargs['queryset'] = ProductRegion.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'service', 'category', 'price_display',
        'discount_badge',
        'delivery_badge', 'credential_type_badge',
        'stock_count', 'is_active', 'is_available', 'thumbnail_preview',
    )
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('thumbnail_preview_large', 'created_at', 'discount_status')
    list_filter = ('service', 'category', 'delivery_type', 'credential_type', 'discount_enabled', 'is_active', 'is_available')
    search_fields = ('title', 'slug', 'description', 'short_description', 'seo_title')
    list_select_related = ('category', 'service')
    list_editable = ('is_active', 'is_available')
    autocomplete_fields = ('category', 'service')
    inlines = [ProductRegionInline, ProductVariantInline]
    save_on_top = True
    list_per_page = 25
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('title', 'slug', 'service', 'category', 'featured_image', 'thumbnail_preview_large'),
            'description': (
                'عنوان خدمت (مثلاً «نتفلیکس پریمیوم ۱ ماهه»). '
                'گروه خدمات و دسته‌بندی اختیاری هستند — با <b>+</b> می‌توانید همین‌جا بسازید.'
            ),
        }),
        ('قیمت و موجودی', {
            'fields': (
                'price', 'allow_quantity', 'is_active', 'is_available',
                'discount_enabled', 'discount_percent', 'discount_start_at', 'discount_end_at', 'discount_status',
            ),
            'description': (
                '«قیمت پایه» فقط وقتی استفاده می‌شود که تنوع قیمتی (پایین صفحه) تعریف <b>نشده</b> باشد. '
                'اگر تنوع دارد، قیمت هر تنوع جداگانه تنظیم می‌شود. '
                'برای تخفیف زمان‌دار، گزینه تخفیف را فعال کنید و درصد/زمان شروع/زمان پایان را وارد کنید.'
            ),
        }),
        ('نحوه تحویل', {
            'fields': ('delivery_type', 'digital_file'),
            'description': (
                '<b>دستی:</b> ادمین بررسی و انجام می‌دهد &nbsp;·&nbsp; '
                '<b>دانلودی:</b> فایل خودکار پس از پرداخت قابل دسترسی می‌شود.'
            ),
        }),
        ('اطلاعات حساب مشتری', {
            'fields': ('credential_type', 'credential_label'),
            'description': 'اگر مشتری باید ایمیل یا رمز حسابش را هنگام خرید وارد کند (مثلاً برای فعال‌سازی روی اکانت مشتری).',
            'classes': ('collapse',),
        }),
        ('توضیحات و ویژگی‌ها', {
            'fields': ('short_description', 'description', 'features'),
            'description': (
                'خلاصه روی کارت خدمت نمایش داده می‌شود. '
                'ویژگی‌ها را هر کدام در یک خط جدا بنویسید (تیک‌دار نشان داده می‌شود).'
            ),
        }),
        ('سئو (SEO)', {
            'fields': ('seo_title', 'seo_description'),
            'description': 'عنوان و توضیحات اختصاصی برای موتورهای جستجو. اگر خالی باشد، از عنوان و خلاصه اصلی استفاده می‌شود.',
            'classes': ('collapse',),
        }),
        ('اطلاعات سیستم', {
            'fields': ('created_at',),
            'classes': ('collapse',),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _stock=Count('items', filter=~Exists(
                AccountItem.objects.filter(pk=OuterRef('items__pk'), allocated=True)
            ))
        )

    @admin.display(description='قیمت', ordering='price')
    def price_display(self, obj):
        return format_html('<span style="font-weight:600;">{} <small>تومان</small></span>', f'{obj.price:,.0f}')

    @admin.display(description='تخفیف')
    def discount_badge(self, obj):
        if obj.is_discount_active:
            return format_html(
                '<span class="status-badge status-badge--danger">{}% فعال</span>',
                obj.discount_percent,
            )
        if obj.is_discount_configured:
            return format_html('<span class="status-badge status-badge--warning">زمان‌بندی شده</span>')
        return format_html('<span class="status-badge status-badge--muted">{}</span>', 'ندارد')

    @admin.display(description='وضعیت تخفیف')
    def discount_status(self, obj):
        if obj is None:
            return 'ابتدا محصول را ذخیره کنید'
        if not obj.is_discount_configured:
            return 'تخفیفی تنظیم نشده است'
        if obj.is_discount_active:
            if obj.discount_end_at:
                end_at = timezone.localtime(obj.discount_end_at).strftime('%Y-%m-%d %H:%M')
                return f'فعال تا {end_at}'
            return 'فعال (بدون زمان پایان)'
        if obj.discount_start_at and timezone.now() < obj.discount_start_at:
            start_at = timezone.localtime(obj.discount_start_at).strftime('%Y-%m-%d %H:%M')
            return f'زمان‌بندی شده از {start_at}'
        if obj.discount_end_at and timezone.now() >= obj.discount_end_at:
            return 'پایان یافته'
        return 'غیرفعال'

    @admin.display(description='موجودی')
    def stock_count(self, obj):
        available = obj.items.filter(allocated=False).count()
        total = obj.items.count()
        if available == 0 and total > 0:
            return format_html('<span class="status-badge status-badge--danger">ناموجود ({}/{})</span>', available, total)
        if available == 0:
            return format_html('<span class="status-badge status-badge--muted">{}</span>', 'بدون آیتم')
        return format_html('<span class="status-badge status-badge--success">{} / {}</span>', available, total)

    @admin.display(description='تصویر')
    def thumbnail_preview(self, obj):
        if obj.featured_image:
            return format_html(
                '<img src="{}" style="width:48px;height:48px;object-fit:cover;border-radius:6px;" />',
                obj.featured_image.url)
        return '—'

    @admin.display(description='پیش‌نمایش تصویر')
    def thumbnail_preview_large(self, obj):
        if obj.featured_image:
            return format_html(
                '<img src="{}" style="max-width:300px;max-height:200px;border-radius:8px;" />',
                obj.featured_image.url)
        return '(بدون تصویر)'

    @admin.display(description='حساب مشتری', ordering='credential_type')
    def credential_type_badge(self, obj):
        if obj.credential_type == Product.CREDENTIAL_EMAIL_PASS:
            return format_html('<span class="status-badge status-badge--warning">{}</span>', 'ایمیل + رمز')
        if obj.credential_type == Product.CREDENTIAL_EMAIL:
            return format_html('<span class="status-badge status-badge--success">{}</span>', 'فقط ایمیل')
        return format_html('<span class="status-badge status-badge--muted">{}</span>', 'ندارد')

    @admin.display(description='تنوع‌ها')
    def variants_count(self, obj):
        count = obj.variants.filter(is_active=True).count()
        if count > 0:
            return format_html('<span class="status-badge status-badge--success">{} تنوع</span>', count)
        return format_html('<span class="status-badge status-badge--muted">{}</span>', 'بدون تنوع')

    @admin.display(description='تحویل', ordering='delivery_type')
    def delivery_badge(self, obj):
        if obj.delivery_type == Product.DELIVERY_DIGITAL:
            return format_html('<span class="status-badge status-badge--success">{}</span>', '📁 دانلودی')
        return format_html('<span class="status-badge status-badge--warning">{}</span>', '✉️ دستی')


# ── گروه خدمات (دسته‌بندی سرویسی) ──────────────────

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'active', 'order', 'products_count', 'view_products_link', 'logo_preview')
    prepopulated_fields = {'slug': ('name',)}
    list_filter = ('active',)
    list_editable = ('active', 'order')
    search_fields = ('name', 'slug', 'description')
    save_on_top = True
    fieldsets = (
        (None, {
            'fields': ('name', 'slug', 'description'),
            'description': (
                'گروه‌بندی خدمات (مثلاً «نتفلیکس»، «اسپاتیفای»). '
                'برای مدیریت جزئیات هر خدمت، از بخش <b>«خدمات»</b> استفاده کنید.'
            ),
        }),
        ('تصویر و آیکون', {
            'fields': ('featured_image', 'icon'),
            'description': 'لوگو یا تصویر گروه — اگر آپلود نشود از آیکون CSS استفاده می‌شود.',
        }),
        ('وضعیت', {
            'fields': ('active', 'order'),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_products_count=Count('products'))

    @admin.display(description='تعداد خدمت', ordering='_products_count')
    def products_count(self, obj):
        return obj._products_count

    @admin.display(description='مشاهده خدمات')
    def view_products_link(self, obj):
        url = f'{reverse("admin:shop_product_changelist")}?service__id__exact={obj.pk}'
        count = getattr(obj, '_products_count', 0)
        if count > 0:
            return format_html('<a href="{}">{} خدمت →</a>', url, count)
        return format_html('<span style="color:#9ca3af;">{}</span>', '—')

    @admin.display(description='لوگو')
    def logo_preview(self, obj):
        if obj.featured_image:
            return format_html(
                '<img src="{}" style="width:40px;height:40px;object-fit:contain;border-radius:6px;background:#f9fafb;padding:2px;" />',
                obj.featured_image.url)
        return '—'


# ── آیتم اکانت ─────────────────────────────────────

@admin.register(AccountItem)
class AccountItemAdmin(admin.ModelAdmin):
    list_display = ('product', 'allocated_badge', 'created_at')
    list_filter = ('allocated', 'created_at', 'product')
    search_fields = ('product__title',)
    readonly_fields = ('username_encrypted', 'password_encrypted', 'notes_encrypted')
    list_select_related = ('product',)

    @admin.display(description='وضعیت', ordering='allocated')
    def allocated_badge(self, obj):
        if obj.allocated:
            return format_html('<span class="status-badge status-badge--warning">{}</span>', 'تخصیص‌یافته')
        return format_html('<span class="status-badge status-badge--success">{}</span>', 'آزاد')


# ── آیتم سفارش (Inline) ────────────────────────────

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    fields = ('product', 'variant_name', 'region_name', 'quantity', 'price', 'customer_email', 'customer_password', 'account_item')
    readonly_fields = ('account_item',)
    extra = 0
    show_change_link = True
    autocomplete_fields = ('product',)


# ── سفارش ───────────────────────────────────────────

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    class FailedPaymentFilter(admin.SimpleListFilter):
        title = 'تراکنش ناموفق'
        parameter_name = 'failed_payment'

        def lookups(self, request, model_admin):
            return (('yes', 'دارد'), ('no', 'ندارد'))

        def queryset(self, request, queryset):
            value = self.value()
            if value == 'yes':
                return queryset.filter(failed_payment_exists=True)
            if value == 'no':
                return queryset.filter(failed_payment_exists=False)
            return queryset

    list_display = (
        'order_number',
        'id',
        'user',
        'total_display',
        'items_count',
        'order_status_badge',
        'payment_status_badge',
        'related_transactions_link',
        'created_at',
    )
    list_filter = ('status', 'paid', 'created_at', FailedPaymentFilter)
    search_fields = (
        'order_number',
        'id',
        'user__username',
        'user__email',
        'customer_name',
        'customer_phone',
        'customer_email',
    )
    list_select_related = ('user',)
    date_hierarchy = 'created_at'
    inlines = [OrderItemInline]
    fieldsets = (
        ('وضعیت سفارش', {'fields': ('order_number', 'status', 'paid', 'status_updated_at')}),
        ('اطلاعات مشتری', {'fields': ('user', 'customer_name', 'customer_phone', 'customer_email')}),
        ('آدرس تحویل', {
            'fields': ('shipping_address',),
            'classes': ('collapse',),
        }),
        ('جزئیات مالی', {'fields': ('subtotal_amount', 'vat_percent_applied', 'vat_amount', 'total', 'created_at')}),
    )
    readonly_fields = ('order_number', 'created_at', 'status_updated_at', 'subtotal_amount', 'vat_percent_applied', 'vat_amount')

    def get_queryset(self, request):
        failed_tx = TransactionLog.objects.filter(order=OuterRef('pk'), success=False)
        return super().get_queryset(request).annotate(
            failed_payment_exists=Exists(failed_tx),
            _items_count=Count('items'),
        )

    @admin.display(description='مبلغ', ordering='total')
    def total_display(self, obj):
        return format_html('<strong>{}</strong> <small>تومان</small>', f'{obj.total:,.0f}')

    @admin.display(description='اقلام', ordering='_items_count')
    def items_count(self, obj):
        count = getattr(obj, '_items_count', obj.items.count())
        return format_html('<span title="{} آیتم">{}</span>', count, count)

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
            css_class, obj.get_status_display())

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
            return '–'
        url = f'{reverse("admin:shop_transactionlog_changelist")}?order__id__exact={obj.pk}'
        return format_html('<a class="admin-row-action" href="{}">مشاهده تراکنش‌ها</a>', url)


# ── تراکنش ──────────────────────────────────────────

@admin.register(TransactionLog)
class TransactionLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'order_link', 'provider', 'success_status', 'created_at')
    list_filter = ('provider', 'success', 'created_at')
    search_fields = ('id', 'provider', 'order__id')
    list_select_related = ('order',)
    readonly_fields = ('order', 'provider', 'payload', 'success', 'created_at')
    date_hierarchy = 'created_at'

    @admin.display(description='نتیجه', ordering='success')
    def success_status(self, obj):
        if obj.success:
            return format_html('<span class="status-badge status-badge--success">{}</span>', 'موفق')
        return format_html('<span class="status-badge status-badge--danger">{}</span>', 'ناموفق')

    @admin.display(description='سفارش', ordering='order')
    def order_link(self, obj):
        if not obj.order_id:
            return '–'
        url = reverse('admin:shop_order_change', args=[obj.order_id])
        return format_html('<a href="{}">سفارش #{}</a>', url, obj.order_id)
