from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from datetime import timedelta

from .models import Post, PostFAQ


class PostWindowFilter(admin.SimpleListFilter):
    title = 'بازه زمانی'
    parameter_name = 'window'

    def lookups(self, request, model_admin):
        return (
            ('this_week', 'این هفته'),
            ('this_month', 'این ماه'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'this_week':
            return queryset.filter(created_at__gte=timezone.now() - timedelta(days=7))
        if value == 'this_month':
            return queryset.filter(created_at__gte=timezone.now() - timedelta(days=30))
        return queryset


class PostFAQInline(admin.StackedInline):
    model = PostFAQ
    extra = 0
    fields = ('question', 'answer')
    verbose_name = 'سوال متداول'
    verbose_name_plural = 'سوالات متداول (FAQ)'


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'publish_status', 'image_preview', 'faqs_count', 'created_at')
    inlines = [PostFAQInline]
    prepopulated_fields = {'slug': ('title',)}
    list_filter = ('published', PostWindowFilter, 'created_at')
    search_fields = ('title', 'slug', 'content', 'seo_title')
    actions = ('mark_published', 'mark_unpublished')
    readonly_fields = ('image_preview_large', 'created_at')
    date_hierarchy = 'created_at'
    save_on_top = True
    fieldsets = (
        ('محتوای پست', {
            'fields': ('title', 'slug', 'content', 'published'),
            'description': 'عنوان و محتوای مقاله. می‌توانید از تگ‌های HTML استفاده کنید.',
        }),
        ('تصویر شاخص', {
            'fields': ('featured_image', 'image_preview_large'),
        }),
        ('SEO', {
            'fields': ('seo_title', 'seo_description', 'keywords'),
            'classes': ('collapse',),
            'description': 'کلمات کلیدی به‌صورت خودکار استخراج می‌شوند اگر خالی بگذارید.',
        }),
        ('اطلاعات', {
            'fields': ('created_at',),
            'classes': ('collapse',),
        }),
    )

    def get_queryset(self, request):
        from django.db.models import Count
        return super().get_queryset(request).annotate(_faqs_count=Count('faqs'))

    @admin.display(description='وضعیت انتشار', ordering='published')
    def publish_status(self, obj):
        if obj.published:
            return format_html('<span class="status-badge status-badge--success">{}</span>', 'منتشرشده')
        return format_html('<span class="status-badge status-badge--muted">{}</span>', 'پیش‌نویس')

    @admin.display(description='تصویر')
    def image_preview(self, obj):
        if obj.featured_image:
            return format_html(
                '<img src="{}" style="width:48px;height:48px;object-fit:cover;border-radius:6px;" />',
                obj.featured_image.url)
        return '—'

    @admin.display(description='پیش‌نمایش تصویر')
    def image_preview_large(self, obj):
        if obj.featured_image:
            return format_html(
                '<img src="{}" style="max-width:400px;max-height:200px;border-radius:8px;" />',
                obj.featured_image.url)
        return '(بدون تصویر)'

    @admin.display(description='سوالات', ordering='_faqs_count')
    def faqs_count(self, obj):
        count = getattr(obj, '_faqs_count', obj.faqs.count())
        if count == 0:
            return '–'
        return format_html('<span title="{} سوال">{}</span>', count, count)

    @admin.action(description='انتشار پست‌های انتخاب‌شده')
    def mark_published(self, request, queryset):
        updated = queryset.update(published=True)
        self.message_user(request, f'{updated} پست منتشر شد.')

    @admin.action(description='تبدیل به پیش‌نویس')
    def mark_unpublished(self, request, queryset):
        updated = queryset.update(published=False)
        self.message_user(request, f'{updated} پست به پیش‌نویس برگشت.')


@admin.register(PostFAQ)
class PostFAQAdmin(admin.ModelAdmin):
    list_display = ('question', 'post', 'short_answer')
    search_fields = ('question', 'answer', 'post__title')
    list_select_related = ('post',)
    list_filter = ('post',)

    @admin.display(description='پاسخ (خلاصه)')
    def short_answer(self, obj):
        return obj.answer[:80] + '…' if len(obj.answer) > 80 else obj.answer
