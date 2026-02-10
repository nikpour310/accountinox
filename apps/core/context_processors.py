from django.conf import settings

def site_settings(request):
    try:
        from apps.core.models import SiteSettings
        # Ensure we always provide a SiteSettings instance (create if missing)
        setting_obj = SiteSettings.load()
    except Exception:
        setting_obj = None

    return {
        'site_settings': setting_obj,
        'debug': settings.DEBUG,
        'site_base_url': settings.SITE_BASE_URL if hasattr(settings, 'SITE_BASE_URL') else f"{request.scheme}://{request.get_host()}",
    }