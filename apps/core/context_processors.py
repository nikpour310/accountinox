from django.conf import settings
from django.contrib import messages

def site_settings(request):
    try:
        from apps.core.models import SiteSettings
        # Ensure we always provide a SiteSettings instance (create if missing)
        setting_obj = SiteSettings.load()
    except Exception:
        setting_obj = None

    # Provide active services for the navbar (safe fallback if shop app not available)
    try:
        from apps.shop.models import Service
        # Prefetch related products to avoid N+1 queries when rendering the megamenu
        services = list(Service.objects.filter(active=True).order_by('order', 'name').prefetch_related('products'))
    except Exception:
        services = []

    # Footer links (grouped as quick / legal)
    try:
        from apps.core.models import FooterLink
        footer_links_quick = list(FooterLink.objects.filter(is_active=True, column='quick'))
        footer_links_legal = list(FooterLink.objects.filter(is_active=True, column='legal'))
    except Exception:
        footer_links_quick = []
        footer_links_legal = []

    # Cart item count for navbar badge
    cart_count = 0
    try:
        raw_cart = request.session.get('cart', {})
        if isinstance(raw_cart, dict):
            cart_count = sum(int(v) for v in raw_cart.values() if str(v).isdigit() and int(v) > 0)
    except Exception:
        cart_count = 0

    # Google OAuth availability (either env-based APP config or DB SocialApp)
    google_oauth_ready = False
    try:
        provider_cfg = getattr(settings, 'SOCIALACCOUNT_PROVIDERS', {}).get('google', {})
        app_cfg = provider_cfg.get('APP') or {}
        env_ready = bool(str(app_cfg.get('client_id', '')).strip() and str(app_cfg.get('secret', '')).strip())
    except Exception:
        env_ready = False

    if env_ready:
        google_oauth_ready = True
    else:
        try:
            from allauth.socialaccount.models import SocialApp
            from django.contrib.sites.models import Site

            current_site = Site.objects.get_current(request)
            google_oauth_ready = SocialApp.objects.filter(provider='google', sites=current_site).exists()
        except Exception:
            google_oauth_ready = False

    return {
        'site_settings': setting_obj,
        'debug': settings.DEBUG,
        'site_base_url': settings.SITE_BASE_URL if hasattr(settings, 'SITE_BASE_URL') else f"{request.scheme}://{request.get_host()}",
        'services': services,
        'footer_links_quick': footer_links_quick,
        'footer_links_legal': footer_links_legal,
        'cart_count': cart_count,
        'google_oauth_ready': google_oauth_ready,
    }


def auth_feedback(request):
    """
    Convert auth/session system flags into one-time user-facing flash messages.
    """
    timeout_reason = request.session.pop('core_idle_timeout_reason', None)
    if timeout_reason == 'staff':
        messages.warning(request, 'به دلیل عدم فعالیت، نشست مدیریتی شما به صورت خودکار بسته شد.')
        request.session.modified = True
    elif timeout_reason == 'user':
        messages.warning(request, 'به دلیل عدم فعالیت، از حساب خود خارج شدید. لطفا دوباره وارد شوید.')
        request.session.modified = True
    return {}
