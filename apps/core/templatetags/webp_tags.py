from django import template
from django.utils.safestring import mark_safe
from django.conf import settings
import os
from html import escape

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
def prefer_webp(context, image, css_class='', alt='', loading='', width='', height=''):
    """Render a <picture> that prefers WebP if a .webp sibling exists.

    `image` may be a Django ImageField, a URL string, or template variable with `.url`.
    """
    def _dim(value):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return ''
        return str(value) if value > 0 else ''

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

    resolved_width = _dim(width) or _dim(getattr(image, 'width', ''))
    resolved_height = _dim(height) or _dim(getattr(image, 'height', ''))

    attrs = []
    if css_class:
        attrs.append(f'class="{escape(str(css_class), quote=True)}"')
    attrs.append(f'alt="{escape(str(alt or ""), quote=True)}"')
    if loading:
        attrs.append(f'loading="{escape(str(loading), quote=True)}"')
    if resolved_width:
        attrs.append(f'width="{resolved_width}"')
    if resolved_height:
        attrs.append(f'height="{resolved_height}"')

    img_attrs = ' '.join(attrs)
    escaped_url = escape(url, quote=True)
    escaped_webp_url = escape(webp_url, quote=True)

    if has_webp:
        html = (
            f"<picture>\n"
            f"  <source type=\"image/webp\" srcset=\"{escaped_webp_url}\">\n"
            f"  <img src=\"{escaped_url}\" {img_attrs}>\n"
            f"</picture>"
        )
    else:
        html = f"<img src=\"{escaped_url}\" {img_attrs}>"

    # ensure responses that vary by Accept are cache-friendly; middleware will add Vary header
    return mark_safe(html)
