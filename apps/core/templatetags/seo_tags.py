from django import template
from django.conf import settings
from django.utils import timezone
from django.utils.safestring import mark_safe

import datetime as _dt
import json

register = template.Library()

_JALALI_MONTHS_FA = (
    'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
    'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند',
)


def _gregorian_to_jalali(gy: int, gm: int, gd: int):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        (365 * gy)
        + ((gy2 + 3) // 4)
        - ((gy2 + 99) // 100)
        + ((gy2 + 399) // 400)
        - 80
        + gd
        + g_d_m[gm - 1]
    )
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def _format_jalali(jy: int, jm: int, jd: int, dt: _dt.datetime, fmt: str):
    token_map = {
        'Y': f'{jy:04d}',
        'y': f'{jy % 100:02d}',
        'm': f'{jm:02d}',
        'n': str(jm),
        'd': f'{jd:02d}',
        'j': str(jd),
        'F': _JALALI_MONTHS_FA[jm - 1],
        'H': f'{dt.hour:02d}',
        'i': f'{dt.minute:02d}',
        's': f'{dt.second:02d}',
    }
    out = []
    escaped = False
    for ch in fmt:
        if escaped:
            out.append(ch)
            escaped = False
            continue
        if ch == '\\':
            escaped = True
            continue
        out.append(token_map.get(ch, ch))
    return ''.join(out)


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


def _jsonld_safe(data):
    def _prune_none(value):
        if isinstance(value, dict):
            return {
                key: _prune_none(item)
                for key, item in value.items()
                if item is not None and item != ''
            }
        if isinstance(value, list):
            return [item for item in (_prune_none(item) for item in value) if item is not None and item != '']
        return value

    cleaned = _prune_none(data)
    payload = json.dumps(cleaned, ensure_ascii=False, separators=(',', ':'))
    return mark_safe(payload.replace('</', '<\\/'))


@register.simple_tag(takes_context=True)
def organization_jsonld(context):
    site_settings = context.get('site_settings')
    base_url = (context.get('site_base_url') or getattr(settings, 'SITE_BASE_URL', '') or '').rstrip('/')
    site_name = 'Accountinox'
    if site_settings:
        site_name = (
            getattr(site_settings, 'brand_wordmark_fa', None)
            or getattr(site_settings, 'site_name', None)
            or site_name
        )

    logo_url = ''
    if site_settings and getattr(site_settings, 'logo', None):
        try:
            logo_url = abs_url(site_settings.logo.url)
        except Exception:
            logo_url = ''

    same_as = []
    if site_settings:
        for field_name in ('instagram_url', 'telegram_channel_url', 'telegram_admin_url'):
            value = getattr(site_settings, field_name, '')
            if value and str(value).startswith(('http://', 'https://')):
                same_as.append(value)

    contact_points = []
    if site_settings:
        phone = getattr(site_settings, 'phone', '')
        if phone:
            contact_points.append({
                '@type': 'ContactPoint',
                'telephone': str(phone),
                'contactType': 'customer support',
                'availableLanguage': 'fa-IR',
            })

    data = {
        '@context': 'https://schema.org',
        '@type': 'Organization',
        'name': site_name,
        'url': base_url,
        'logo': logo_url,
        'sameAs': same_as,
        'contactPoint': contact_points,
    }
    return _jsonld_safe(data)


@register.simple_tag(takes_context=True)
def website_jsonld(context):
    site_settings = context.get('site_settings')
    base_url = (context.get('site_base_url') or getattr(settings, 'SITE_BASE_URL', '') or '').rstrip('/')
    site_name = 'Accountinox'
    if site_settings:
        site_name = (
            getattr(site_settings, 'brand_wordmark_fa', None)
            or getattr(site_settings, 'site_name', None)
            or site_name
        )

    data = {
        '@context': 'https://schema.org',
        '@type': 'WebSite',
        'name': site_name,
        'url': base_url,
        'inLanguage': 'fa-IR',
        'potentialAction': {
            '@type': 'SearchAction',
            'target': f'{base_url}/search/?q={{search_term_string}}' if base_url else None,
            'query-input': 'required name=search_term_string',
        },
    }
    return _jsonld_safe(data)


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


@register.filter(name='jdate', is_safe=True)
def jdate(value, fmt='Y/m/d H:i'):
    """Format datetime/date to Jalali (Solar Hijri) using a Django-like pattern."""
    if not value:
        return ''
    dt = value
    if isinstance(dt, _dt.date) and not isinstance(dt, _dt.datetime):
        dt = _dt.datetime(dt.year, dt.month, dt.day)
    if not isinstance(dt, _dt.datetime):
        return value
    if timezone.is_aware(dt):
        dt = timezone.localtime(dt)
    jy, jm, jd = _gregorian_to_jalali(dt.year, dt.month, dt.day)
    try:
        return _format_jalali(jy, jm, jd, dt, fmt or 'Y/m/d H:i')
    except Exception:
        return value


@register.filter(name='jalali', is_safe=True)
def jalali(value, fmt='Y/m/d H:i'):
    return jdate(value, fmt)
