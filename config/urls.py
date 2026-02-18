from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from django.http import HttpResponse, HttpResponseNotFound, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.generic import TemplateView
from django.contrib.staticfiles import finders
from datetime import datetime, timezone
from .sitemaps import StaticViewSitemap, BlogSitemap, ProductSitemap
from apps.accounts import views as account_views

sitemaps = {
    'static': StaticViewSitemap,
    'blog': BlogSitemap,
    'products': ProductSitemap,
}

# Healthcheck endpoint for monitoring (G-4)
@csrf_exempt
@require_http_methods(['GET', 'HEAD'])
def healthcheck(request):
    """
    Lightweight health check endpoint for monitoring scripts and uptime services.
    Returns 200 OK if application is running.
    """
    return JsonResponse({
        'status': 'ok',
        'timestamp': datetime.now(timezone.utc).isoformat(),
    })


@require_http_methods(['GET'])
def service_worker(request):
    sw_path = finders.find('sw.js')
    if not sw_path:
        return HttpResponseNotFound('Service worker not found')
    with open(sw_path, 'r', encoding='utf-8') as sw_file:
        response = HttpResponse(sw_file.read(), content_type='application/javascript')
        response['Service-Worker-Allowed'] = '/'
        return response

urlpatterns = [
    path('healthz/', healthcheck, name='healthcheck'),  # G-4: Monitoring endpoint
    path('sw.js', service_worker, name='service_worker'),
    # Smart password reset (must be before allauth include to override default path)
    path('accounts/password/reset/', account_views.smart_password_reset, name='account_reset_password'),
    path('accounts/password/reset/phone/verify/', account_views.smart_password_reset_phone_verify, name='account_reset_password_phone_verify'),
    path('accounts/password/reset/phone/resend/', account_views.smart_password_reset_phone_resend, name='account_reset_password_phone_resend'),
    path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain'), name='robots_txt'),
    path('terms/', TemplateView.as_view(template_name='terms.html'), name='terms'),
    path('privacy/', TemplateView.as_view(template_name='privacy.html'), name='privacy'),
    path('admin/', admin.site.urls),
    path('account/', include(('apps.accounts.urls', 'account_panel'), namespace='account_panel')),
    path('accounts/', include('apps.accounts.urls')),
    path('accounts/', include('allauth.urls')),
    path('', include('apps.core.urls')),
    path('shop/', include('apps.shop.urls')),
    path('blog/', include('apps.blog.urls')),
    path('support/', include('apps.support.urls')),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='sitemap'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
else:
    # Serve static/media locally when running runserver with DEBUG=False (testing 404 etc.)
    # In production (cPanel/nginx), the web server handles these paths.
    import sys
    if 'runserver' in sys.argv:
        from django.contrib.staticfiles.urls import staticfiles_urlpatterns
        urlpatterns += staticfiles_urlpatterns()
        from django.views.static import serve as static_serve
        from django.urls import re_path
        urlpatterns += [
            re_path(r'^media/(?P<path>.*)$', static_serve, {'document_root': settings.MEDIA_ROOT}),
        ]

handler404 = 'apps.core.views.custom_404'
