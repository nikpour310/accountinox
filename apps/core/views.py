from django.shortcuts import render
from django.db.models import Q
from .models import GlobalFAQ, HeroBanner, TrustStat, FeatureCard, FooterLink


def landing(request):
    try:
        faqs = list(GlobalFAQ.objects.all()[:10])
    except Exception:
        faqs = []

    # Active hero banners for the slider
    try:
        banners = list(HeroBanner.objects.filter(is_active=True)[:10])
    except Exception:
        banners = []

    # Trust stats strip
    try:
        trust_stats = list(TrustStat.objects.filter(is_active=True)[:6])
    except Exception:
        trust_stats = []

    # Feature cards
    try:
        feature_cards = list(FeatureCard.objects.filter(is_active=True)[:8])
    except Exception:
        feature_cards = []

    # Latest products for the landing page grid
    try:
        from apps.shop.models import Product
        latest_products = list(Product.objects.select_related(
            'category', 'service'
        ).filter(is_active=True).order_by('-created_at', '-pk')[:8])
    except Exception:
        latest_products = []

    # Service groups for landing showcase
    try:
        from apps.shop.models import Service
        from django.db import models
        from django.db.models import Count
        services = list(Service.objects.filter(active=True).annotate(
            products_count=Count('products', filter=models.Q(products__is_active=True))
        ).order_by('order', 'name')[:6])
    except Exception:
        services = []

    # Latest published blog posts
    try:
        from apps.blog.models import Post
        latest_posts = list(Post.objects.filter(published=True).order_by('-created_at')[:3])
    except Exception:
        latest_posts = []

    return render(request, 'landing.html', {
        'faqs': faqs,
        'banners': banners,
        'trust_stats': trust_stats,
        'feature_cards': feature_cards,
        'latest_products': latest_products,
        'services': services,
        'latest_posts': latest_posts,
    })


def terms(request):
    return render(request, 'terms.html')


def privacy(request):
    return render(request, 'privacy.html')


def contact(request):
    return render(request, 'contact.html')


def site_search(request):
    """
    Unified site search across products, blog posts, and services.
    Supports ?q= query parameter with minimum 2 characters.
    """
    query = request.GET.get('q', '').strip()
    products = []
    posts = []
    services = []
    total = 0

    if len(query) >= 2:
        # Search products
        try:
            from apps.shop.models import Product
            products = list(
                Product.objects.filter(
                    Q(title__icontains=query)
                    | Q(description__icontains=query)
                    | Q(seo_title__icontains=query)
                    | Q(category__name__icontains=query)
                )
                .select_related('category', 'service')
                .distinct()[:12]
            )
        except Exception:
            pass

        # Search blog posts (only published)
        try:
            from apps.blog.models import Post
            posts = list(
                Post.objects.filter(
                    Q(published=True),
                    Q(title__icontains=query)
                    | Q(content__icontains=query)
                    | Q(seo_title__icontains=query)
                    | Q(keywords__icontains=query),
                ).distinct()[:12]
            )
        except Exception:
            pass

        # Search services
        try:
            from apps.shop.models import Service
            services = list(
                Service.objects.filter(
                    Q(active=True),
                    Q(name__icontains=query)
                    | Q(description__icontains=query),
                ).distinct()[:6]
            )
        except Exception:
            pass

        total = len(products) + len(posts) + len(services)

    return render(request, 'search_results.html', {
        'query': query,
        'products': products,
        'posts': posts,
        'services': services,
        'total': total,
    })


def custom_404(request, exception):
    return render(request, '404.html', status=404)
