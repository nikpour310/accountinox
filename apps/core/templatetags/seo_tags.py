from django import template
from django.conf import settings

register = template.Library()


@register.filter(is_safe=True)
def abs_url(value):
    """Return an absolute URL.

    - If `value` already starts with http(s):// return as-is.
    - If it starts with '//' (protocol-relative) try to prepend scheme from SITE_BASE_URL.
    - If it starts with '/', prepend SITE_BASE_URL.
    - Otherwise prepend SITE_BASE_URL + '/'.
    """
    if not value:
        return ''
    val = str(value)
    if val.startswith('http://') or val.startswith('https://'):
        return val
    if val.startswith('//'):
        base = getattr(settings, 'SITE_BASE_URL', '')
        if base and base.startswith('http'):
            scheme = base.split(':', 1)[0]
            return f"{scheme}:{val}"
        return val
    base = getattr(settings, 'SITE_BASE_URL', '').rstrip('/')
    if val.startswith('/'):
        return f"{base}{val}"
    return f"{base}/{val}"


@register.filter(is_safe=True)
def image_alt(image, alt):
    """Return a safe alt text for an image.

    If `alt` provided and non-empty, return it. Otherwise, try to infer from
    the image's model instance (common attrs: title, name, slug). Falls back
    to empty string for decorative images.
    """
    if alt:
        return alt
    try:
        inst = getattr(image, 'instance', None)
        if inst:
            return getattr(inst, 'title', None) or getattr(inst, 'name', None) or getattr(inst, 'slug', '')
    except Exception:
        pass
    return ''


@register.simple_tag(takes_context=True)
def canonical_url(context, keep_page=True):
    """Build a safe canonical absolute URL for the current request.

    Rules:
    - Strip common tracking params (utm_*, gclid, fbclid, ref, session, tracking, coupon).
    - Strip variation params (sort, order, currency) by default.
    - Optionally keep `page` when `keep_page=True` to preserve pagination in canonical.
    Returns absolute URL using `settings.SITE_BASE_URL` when available, else request host.
    """
    request = context.get('request')
    if not request:
        return ''

    base = getattr(settings, 'SITE_BASE_URL', '') or f"{request.scheme}://{request.get_host()}"
    base = base.rstrip('/')
    path = request.path

    # Parameters to always strip
    strip_params = {
        'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
        'gclid', 'fbclid', 'ref', 'session', 'tracking', 'coupon',
        'sort', 'order', 'currency'
    }

    # Build allowed params dict
    allowed = {}
    params = request.GET
    if keep_page and params.get('page'):
        # include page only if it's a positive integer (basic check)
        page = params.get('page')
        if page.isdigit() and int(page) > 1:
            allowed['page'] = page
        elif page.isdigit() and int(page) == 1:
            # normally omit page=1 from canonical
            pass

    from urllib.parse import urlencode
    qs = urlencode(allowed)
    return f"{base}{path}{'?' + qs if qs else ''}"


@register.filter(is_safe=True)
def price_format(value):
    """Format a number with comma thousand separators (works in fa locale).

    Example: 250000 → '250,000'
    """
    try:
        # Convert to int if possible for clean output
        num = int(float(value))
        return f'{num:,}'
    except (ValueError, TypeError):
        return value
