from django.urls import reverse
from django.contrib.sitemaps import Sitemap
from apps.blog.models import Post
from apps.shop.models import Product


class StaticViewSitemap(Sitemap):
    priority = 0.5
    changefreq = 'daily'

    def items(self):
        return [
            'core:landing',
            'core:terms',
            'core:privacy',
            'core:contact',
            'shop:product_list',
            'blog:post_list',
            'support:chat',
        ]

    def location(self, item):
        return reverse(item)


class BlogSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.6

    def items(self):
        return Post.objects.filter(published=True).order_by('-created_at')

    def lastmod(self, obj):
        # prefer `updated_at` if model provides it, otherwise fall back to created_at
        return getattr(obj, 'updated_at', obj.created_at)


class ProductSitemap(Sitemap):
    changefreq = 'daily'
    priority = 0.7

    def items(self):
        # Only include products that are active and available for sale
        return Product.objects.filter(is_active=True, is_available=True).order_by('-id')

    def location(self, item):
        return reverse('shop:product_detail', args=[item.slug])
