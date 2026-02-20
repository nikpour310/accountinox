from django.urls import reverse
from django.contrib.sitemaps import Sitemap


class StaticViewSitemap(Sitemap):
    priority = 0.5
    changefreq = 'daily'

    def items(self):
        return [
            'core:landing',
            'core:cookies',
            'core:terms',
            'core:privacy',
            'core:contact',
            'shop:product_list',
            'shop:service_list',
            'blog:post_list',
        ]

    def location(self, item):
        return reverse(item)


class BlogSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.6

    def items(self):
        try:
            from apps.blog.models import Post
            return Post.objects.filter(published=True).order_by('-created_at')
        except Exception:
            return []

    def lastmod(self, obj):
        # prefer `updated_at` if model provides it, otherwise fall back to created_at
        return getattr(obj, 'updated_at', obj.created_at)


class ProductSitemap(Sitemap):
    changefreq = 'daily'
    priority = 0.7

    def items(self):
        try:
            from apps.shop.models import Product
            return Product.objects.filter(is_active=True, is_available=True).order_by('-id')
        except Exception:
            return []

    def location(self, item):
        return reverse('shop:product_detail', args=[item.slug])


class ServiceSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.6

    def items(self):
        try:
            from apps.shop.models import Service
            return Service.objects.filter(active=True).order_by('order', 'name')
        except Exception:
            return []

    def location(self, item):
        return reverse('shop:service_detail', args=[item.slug])
