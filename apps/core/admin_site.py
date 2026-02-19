"""
Custom AdminSite for Accountinox.
Provides dashboard statistics, command-bar links, role-based priority actions,
and default favorites to the admin templates.
"""
from django.contrib import admin
from django.contrib.admin.apps import AdminConfig as DjangoAdminConfig
from django.conf import settings
from django.db.models import Avg, Count, Q
from django.urls import reverse, NoReverseMatch
from django.utils import timezone
from datetime import timedelta


class AccountinoxAdminConfig(DjangoAdminConfig):
    """Replace the default AdminConfig so all @admin.register() use our custom site."""
    default_site = 'apps.core.admin_site.AccountinoxAdminSite'


class AccountinoxAdminSite(admin.AdminSite):
    site_header = 'اکانتینوکس — پنل مدیریت'
    site_title = 'پنل اکانتینوکس'
    index_title = 'داشبورد مدیریت'

    def each_context(self, request):
        ctx = super().each_context(request)
        user = request.user

        # Brand colors from settings (with fallbacks)
        ctx['admin_brand_primary'] = getattr(settings, 'ADMIN_BRAND_PRIMARY', '') or '#1ABBC8'
        ctx['admin_brand_secondary'] = getattr(settings, 'ADMIN_BRAND_SECONDARY', '') or '#0468BD'
        ctx['admin_brand_accent'] = getattr(settings, 'ADMIN_BRAND_ACCENT', '') or '#45E2CC'
        ctx['admin_is_debug'] = settings.DEBUG

        # Primary role detection
        ctx['admin_primary_role'] = self._detect_role(user)

        # Dashboard stats (only computed on index page for performance)
        ctx['admin_dashboard_stats'] = self._get_dashboard_stats(user)

        # Command bar links
        ctx['admin_command_links'] = self._get_command_links(user)

        # Default favorites for noscript fallback
        ctx['admin_default_favorites'] = self._get_default_favorites(user)

        return ctx

    def _detect_role(self, user):
        if not user.is_authenticated:
            return 'anonymous'
        if user.is_superuser:
            return 'owner'
        groups = set(user.groups.values_list('name', flat=True))
        if 'Owner' in groups:
            return 'owner'
        if 'Support Agent' in groups:
            return 'support'
        if 'CRM' in groups:
            return 'crm'
        if 'Content' in groups or 'Editor' in groups:
            return 'content'
        return 'staff'

    def _get_dashboard_stats(self, user):
        stats = {}
        if not user.is_authenticated or not user.is_staff:
            return stats

        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)

        # Support stats
        try:
            from apps.support.models import ChatSession, ChatMessage, SupportRating
            stats['support_active_sessions'] = ChatSession.objects.filter(is_active=True).count()
            stats['support_unread_messages'] = ChatMessage.objects.filter(
                is_from_user=True, read=False,
                session__is_active=True,
            ).count()
            avg = SupportRating.objects.filter(
                created_at__gte=thirty_days_ago,
            ).aggregate(avg=Avg('score'))['avg']
            stats['support_avg_rating_30d'] = round(avg, 1) if avg else '-'
        except Exception:
            pass

        # Shop stats
        try:
            from apps.shop.models import Order, Product, TransactionLog, AccountItem
            stats['shop_pending_orders'] = Order.objects.filter(paid=False).count()
            stats['shop_total_orders'] = Order.objects.count()
            stats['shop_failed_payments'] = TransactionLog.objects.filter(
                success=False,
                created_at__gte=thirty_days_ago,
            ).count()
            stats['shop_products_count'] = Product.objects.count()
            stats['shop_free_items'] = AccountItem.objects.filter(allocated=False).count()
        except Exception:
            pass

        # Blog stats
        try:
            from apps.blog.models import Post, PostFAQ
            stats['blog_total_posts'] = Post.objects.count()
            stats['blog_draft_posts'] = Post.objects.filter(published=False).count()
            stats['blog_faq_count'] = PostFAQ.objects.count()
        except Exception:
            pass

        # Accounts stats
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            stats['accounts_total_users'] = User.objects.count()
            stats['accounts_active_users_30d'] = User.objects.filter(
                last_login__gte=thirty_days_ago,
            ).count()
        except Exception:
            pass

        # Core stats
        try:
            from apps.core.models import HeroBanner, TrustStat, FeatureCard, FooterLink
            stats['core_active_banners'] = HeroBanner.objects.filter(is_active=True).count()
            stats['core_trust_stats'] = TrustStat.objects.filter(is_active=True).count()
            stats['core_feature_cards'] = FeatureCard.objects.filter(is_active=True).count()
            stats['core_footer_links'] = FooterLink.objects.filter(is_active=True).count()
        except Exception:
            pass

        return stats

    def _get_command_links(self, user):
        """Generate quick-access links for the command bar."""
        links = []
        if not user.is_authenticated or not user.is_staff:
            return links

        link_defs = [
            # پشتیبانی
            ('support:operator_dashboard', 'پنل اپراتور پشتیبانی', 'اپراتور پشتیبانی زنده چت'),
            ('admin:support_chatsession_changelist', 'صندوق پشتیبانی', 'پشتیبانی چت گفتگو'),
            ('admin:support_supportcontact_changelist', 'مخاطبین پشتیبانی', 'مخاطب تماس'),
            ('admin:support_supportrating_changelist', 'امتیازهای پشتیبانی', 'امتیاز ریتینگ'),
            # سفارش‌ها و مالی
            ('admin:shop_order_changelist', 'سفارش‌ها', 'سفارش خرید فروش'),
            ('admin:shop_transactionlog_changelist', 'تراکنش‌ها', 'تراکنش پرداخت'),
            # محصولات
            ('admin:shop_product_changelist', 'محصولات', 'محصول کالا لیست'),
            ('admin:shop_service_changelist', 'سرویس‌ها', 'سرویس خدمات'),
            ('admin:shop_category_changelist', 'دسته‌بندی‌ها', 'دسته بندی'),
            ('admin:shop_accountitem_changelist', 'آیتم‌های اکانت', 'آیتم اکانت'),
            # بلاگ
            ('admin:blog_post_changelist', 'پست‌های بلاگ', 'بلاگ پست مقاله'),
            ('admin:blog_post_add', 'پست جدید', 'افزودن پست بلاگ'),
            # محتوای سایت
            ('admin:core_herobanner_changelist', 'بنرهای اسلایدر', 'بنر اسلایدر هیرو'),
            ('admin:core_truststat_changelist', 'آمار اعتماد', 'آمار اعتمادسازی'),
            ('admin:core_featurecard_changelist', 'کارت ویژگی‌ها', 'ویژگی فیچر'),
            ('admin:core_footerlink_changelist', 'لینک‌های فوتر', 'فوتر لینک'),
            ('admin:core_globalfaq_changelist', 'سوالات متداول', 'سوال فاق'),
            # تنظیمات و کاربران
            ('admin:core_sitesettings_changelist', 'تنظیمات سایت', 'تنظیمات ست آپ'),
            ('admin:auth_user_changelist', 'کاربران', 'کاربر یوزر'),
            ('admin:auth_group_changelist', 'گروه‌ها و دسترسی', 'گروه دسترسی'),
            ('admin:accounts_profile_changelist', 'پروفایل‌ها', 'پروفایل'),
        ]

        for url_name, label, keywords in link_defs:
            try:
                url = reverse(url_name)
                links.append({'url': url, 'label': label, 'keywords': keywords})
            except NoReverseMatch:
                pass

        return links

    def _get_default_favorites(self, user):
        """Provide default favorites for noscript fallback."""
        if not user.is_authenticated or not user.is_staff:
            return []

        defaults = [
            ('support:operator_dashboard', 'پنل اپراتور پشتیبانی'),
            ('admin:support_chatsession_changelist', 'صندوق پشتیبانی'),
            ('admin:shop_order_changelist', 'سفارش‌ها'),
            ('admin:blog_post_changelist', 'بلاگ'),
            ('admin:core_sitesettings_changelist', 'تنظیمات سایت'),
        ]
        result = []
        for url_name, label in defaults:
            try:
                result.append({'url': reverse(url_name), 'label': label})
            except NoReverseMatch:
                pass
        return result
