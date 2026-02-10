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
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'this_week':
            return queryset.filter(created_at__gte=timezone.now() - timedelta(days=7))
        return queryset


class PostFAQInline(admin.TabularInline):
    model = PostFAQ
    extra = 1


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'publish_status', 'created_at')
    inlines = [PostFAQInline]
    prepopulated_fields = {'slug': ('title',)}
    list_filter = ('published', PostWindowFilter, 'created_at')
    search_fields = ('title', 'slug', 'content', 'seo_title')
    actions = ('mark_published', 'mark_unpublished')

    @admin.display(description='وضعیت انتشار', ordering='published')
    def publish_status(self, obj):
        if obj.published:
            return format_html('<span class="status-badge status-badge--success">{}</span>', 'منتشرشده')
        return format_html('<span class="status-badge status-badge--muted">{}</span>', 'پیش‌نویس')

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
    list_display = ('question', 'post')
    search_fields = ('question', 'answer', 'post__title')
    list_select_related = ('post',)
