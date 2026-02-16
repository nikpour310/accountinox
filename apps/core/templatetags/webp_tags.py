from django import template
from django.utils.safestring import mark_safe
from django.conf import settings
import os

register = template.Library()


def _to_path(url):
    """Convert a media/static url to a filesystem path where possible."""
    if not url:
        return None
    # strip domain if present
    if url.startswith('http'):
        return None
    # media
    if url.startswith(settings.MEDIA_URL):
        rel = url[len(settings.MEDIA_URL):].lstrip('/')
        p = os.path.join(settings.MEDIA_ROOT, rel)
        return p
    # static
    if url.startswith(settings.STATIC_URL):
        rel = url[len(settings.STATIC_URL):].lstrip('/')
        p1 = os.path.join(settings.BASE_DIR, 'static', rel)
        p2 = os.path.join(settings.BASE_DIR, 'staticfiles', rel)
        if os.path.exists(p1):
            return p1
        if os.path.exists(p2):
            return p2
    # relative
    if url.startswith('/'):
        # try as media first then static
        rel = url.lstrip('/')
        p = os.path.join(settings.BASE_DIR, rel)
        if os.path.exists(p):
            return p
    return None


@register.simple_tag(takes_context=True)
def prefer_webp(context, image, css_class='', alt='', loading=''):
    """Render a <picture> that prefers WebP if a .webp sibling exists.

    `image` may be a Django ImageField, a URL string, or template variable with `.url`.
    """
    # resolve image value
    url = ''
    try:
        if hasattr(image, 'url'):
            url = image.url
        else:
            url = str(image)
    except Exception:
        url = str(image or '')

    if not url:
        return ''

    # construct candidate webp url
    root, ext = os.path.splitext(url)
    webp_url = root + '.webp'

    # check filesystem for webp
    webp_path = _to_path(webp_url)
    has_webp = webp_path and os.path.exists(webp_path)

    attrs = []
    if css_class:
        attrs.append(f'class="{css_class}"')
    if alt:
        attrs.append(f'alt="{alt}"')
    if loading:
        attrs.append(f'loading="{loading}"')

    img_attrs = ' '.join(attrs)

    if has_webp:
        html = f"<picture>\n  <source type=\"image/webp\" srcset=\"{webp_url}\">\n  <img src=\"{url}\" {img_attrs}>\n</picture>"
    else:
        html = f"<img src=\"{url}\" {img_attrs}>"

    # ensure responses that vary by Accept are cache-friendly; middleware will add Vary header
    return mark_safe(html)
