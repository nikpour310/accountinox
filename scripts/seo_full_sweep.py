#!/usr/bin/env python3
"""Full sitemap SEO sweep.

Fetches /sitemap.xml from local server (default http://127.0.0.1:8005) and
validates each <loc> URL for HTTP 200, canonical correctness, and JSON-LD.
Writes `seo_full_sweep_summary.json` with counts and failures.

Usage: python scripts/seo_full_sweep.py [base_url]
"""
import sys
import time
import json
import re
from urllib.parse import urlparse, parse_qs

try:
    import requests
except Exception as e:
    print("ERROR: requests library required. Install in venv: pip install requests")
    raise

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8005"
if BASE.endswith('/'):
    BASE = BASE[:-1]
SITEMAP = BASE + '/sitemap.xml'
RATE_DELAY = 0.34  # ~3 requests/sec

locs = []
print('Fetching sitemap:', SITEMAP)
r = requests.get(SITEMAP, timeout=30)
if r.status_code != 200:
    print('Failed to fetch sitemap:', r.status_code)
    sys.exit(2)

# extract <loc> values (handle namespaces and whitespace)
locs = re.findall(r'<loc>\s*(https?://[^<\s]+)\s*</loc>', r.text, re.I)
if not locs:
    print('No <loc> entries found in sitemap')

failures = []
counts = {'total': len(locs), 'failed': 0}

# helper checks
PARAM_LEAK_RE = re.compile(r'(utm_[^=]+|gclid|fbclid)', re.I)
QUERY_PARAM_LEAK_KEYS = ('sort', 'currency')

for i, url in enumerate(locs, start=1):
    time.sleep(RATE_DELAY)
    entry_fail_reasons = []
    entry = {'url': url, 'errors': []}
    try:
        resp = requests.get(url, timeout=30, allow_redirects=True)
    except Exception as e:
        # Retry by mapping the path to the local BASE (useful when sitemap contains
        # non-resolvable hostnames like 'http://accountinox/...' during local QA)
        try:
            parsed = urlparse(url)
            fallback = BASE + parsed.path
            if parsed.query:
                fallback += '?' + parsed.query
            resp = requests.get(fallback, timeout=30, allow_redirects=True)
        except Exception as e2:
            entry['errors'].append({'code': 'HTTP_ERROR', 'msg': str(e)})
            failures.append(entry)
            continue
    if resp.status_code != 200:
        entry['errors'].append({'code': 'HTTP_STATUS', 'msg': f'status={resp.status_code}'})
    html = resp.text
    # canonical checks
    canon_hrefs = re.findall(r'<link[^>]+rel=["\']canonical["\'][^>]*>', html, re.I)
    # extract hrefs
    canon_urls = []
    for tag in canon_hrefs:
        m = re.search(r'href=["\']([^"\']+)["\']', tag, re.I)
        if m:
            canon_urls.append(m.group(1))
    if len(canon_urls) == 0:
        entry['errors'].append({'code': 'CANONICAL_MISSING', 'msg': 'no canonical link'})
    elif len(canon_urls) > 1:
        entry['errors'].append({'code': 'CANONICAL_MULTIPLE', 'msg': f'{len(canon_urls)} canonical links'})
    else:
        canon = canon_urls[0]
        if not canon.startswith('https://'):
            entry['errors'].append({'code': 'CANONICAL_NOT_HTTPS', 'msg': canon})
        # check param leaks
        parsed = urlparse(canon)
        qs = parse_qs(parsed.query)
        for k in qs.keys():
            if PARAM_LEAK_RE.search(k) or any(k.lower().startswith(pk) for pk in QUERY_PARAM_LEAK_KEYS):
                entry['errors'].append({'code': 'CANONICAL_LEAKS', 'msg': f'param={k}'})
        # also check raw for gclid/fbclid in whole canonical
        if PARAM_LEAK_RE.search(canon):
            entry['errors'].append({'code': 'CANONICAL_LEAKS', 'msg': canon})

    # JSON-LD extraction
    scripts = re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.I | re.S)
    if scripts:
        for idx, block in enumerate(scripts, start=1):
            text = block.strip()
            if not text:
                continue
            try:
                data = json.loads(text)
            except Exception as e:
                # try to clean common concatenation errors by splitting on '}{' boundaries
                entry['errors'].append({'code': 'JSONLD_PARSE', 'msg': f'block#{idx} parse error: {str(e)[:200]}'})
                continue
            # Normalize: data can be dict or list
            items = data if isinstance(data, list) else [data]
            for obj in items:
                if not isinstance(obj, dict):
                    continue
                typ = obj.get('@type') or obj.get('type')
                if not typ:
                    continue
                typ = typ.lower()
                if 'product' in typ:
                    # product checks
                    # url
                    purl = obj.get('url')
                    if not purl or not purl.startswith('https://'):
                        entry['errors'].append({'code': 'JSONLD_PRODUCT_URL', 'msg': str(purl)})
                    offers = obj.get('offers')
                    if not offers:
                        entry['errors'].append({'code': 'JSONLD_PRODUCT_OFFERS_MISSING', 'msg': ''})
                    else:
                        # offers can be list or dict
                        off_items = offers if isinstance(offers, list) else [offers]
                        for off in off_items:
                            price = off.get('price')
                            cur = off.get('priceCurrency')
                            avail = off.get('availability')
                            off_url = off.get('url')
                            if price is None:
                                entry['errors'].append({'code': 'JSONLD_PRODUCT_OFFER_PRICE', 'msg': ''})
                            if not cur:
                                entry['errors'].append({'code': 'JSONLD_PRODUCT_OFFER_CURRENCY', 'msg': ''})
                            if not avail:
                                entry['errors'].append({'code': 'JSONLD_PRODUCT_OFFER_AVAILABILITY', 'msg': ''})
                            if not off_url or not off_url.startswith('https://'):
                                entry['errors'].append({'code': 'JSONLD_PRODUCT_OFFER_URL', 'msg': str(off_url)})
                if 'article' in typ or 'newsarticle' in typ or 'blogposting' in typ:
                    # article checks
                    if not obj.get('headline'):
                        entry['errors'].append({'code': 'JSONLD_ARTICLE_HEADLINE', 'msg': ''})
                    if not obj.get('datePublished'):
                        entry['errors'].append({'code': 'JSONLD_ARTICLE_PUBLISHED', 'msg': ''})
                    if not obj.get('dateModified'):
                        entry['errors'].append({'code': 'JSONLD_ARTICLE_MODIFIED', 'msg': ''})
                    aurl = obj.get('url')
                    if not aurl or not aurl.startswith('https://'):
                        entry['errors'].append({'code': 'JSONLD_ARTICLE_URL', 'msg': str(aurl)})
                if 'breadcrumblist' in typ or 'breadcrumb' in typ:
                    elems = obj.get('itemListElement') or obj.get('itemList')
                    if not elems or not isinstance(elems, list):
                        entry['errors'].append({'code': 'JSONLD_BREADCRUMB_MISSING', 'msg': ''})
                    else:
                        last_pos = 0
                        for el in elems:
                            # element might be dict with 'position' and 'item' or 'item' containing dict
                            pos = el.get('position') or (el.get('item') and el.get('item').get('position'))
                            item = el.get('item')
                            if isinstance(item, dict):
                                item_url = item.get('@id') or item.get('id') or item.get('url')
                            else:
                                item_url = item
                            if pos is None:
                                entry['errors'].append({'code': 'JSONLD_BREADCRUMB_POSITION', 'msg': ''})
                            else:
                                try:
                                    pos_i = int(pos)
                                    if pos_i != last_pos + 1:
                                        entry['errors'].append({'code': 'JSONLD_BREADCRUMB_POSITION_ORDER', 'msg': f'{pos_i} after {last_pos}'})
                                    last_pos = pos_i
                                except Exception:
                                    entry['errors'].append({'code': 'JSONLD_BREADCRUMB_POSITION_TYPE', 'msg': str(pos)})
                            if not item_url or not str(item_url).startswith('https://'):
                                entry['errors'].append({'code': 'JSONLD_BREADCRUMB_ITEM_URL', 'msg': str(item_url)})
    else:
        # no script tags — not necessarily an error unless expecting structured data, skip
        pass

    if entry['errors']:
        counts['failed'] += 1
        failures.append(entry)

# write summary
summary = {'counts': counts, 'failures': failures}
with open('seo_full_sweep_summary.json', 'w', encoding='utf-8') as fh:
    json.dump(summary, fh, indent=2, ensure_ascii=False)

print('Done. total=', counts['total'], 'failed=', counts['failed'])
print('Summary written to seo_full_sweep_summary.json')

# --- Extended audit pass (redirects, headers, hreflang, accessibility, fonts, JSON-LD coverage)
EXT_COUNTS = {'total': 0, 'issues': 0}
EXT_FAILURES = []

def check_page_extended(url, html, resp):
    issues = []
    # Redirect chain
    if resp.history:
        chain = [{'code': h.status_code, 'url': h.headers.get('Location') or ''} for h in resp.history]
        issues.append({'code': 'REDIRECT_CHAIN', 'msg': chain})

    # canonical vs final url
    canon_match = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']', html, re.I)
    final_url = resp.url
    if canon_match:
        canon = canon_match.group(1)
        if not canon.startswith('https://'):
            issues.append({'code': 'CANONICAL_NOT_HTTPS_EXT', 'msg': canon})
        # if redirect final differs from canonical path
        if urlparse(canon).path != urlparse(final_url).path:
            issues.append({'code': 'CANONICAL_VS_FINAL_MISMATCH', 'msg': {'canonical': canon, 'final': final_url}})
    else:
        issues.append({'code': 'CANONICAL_MISSING_EXT', 'msg': ''})

    # hreflang
    hreflangs = re.findall(r'<link[^>]+rel=["\']alternate["\'][^>]*hreflang=["\']([^"\']+)["\'][^>]*href=["\']([^"\']+)["\']', html, re.I)
    if hreflangs:
        # check absolute
        for lang, href in hreflangs:
            if not href.startswith('https://'):
                issues.append({'code': 'HREFLANG_NOT_ABSOLUTE', 'msg': {'lang': lang, 'href': href}})

    # security headers
    sec_headers = resp.headers
    if 'strict-transport-security' not in {k.lower() for k in sec_headers.keys()}:
        issues.append({'code': 'HSTS_MISSING', 'msg': ''})
    if 'content-security-policy' not in {k.lower() for k in sec_headers.keys()}:
        issues.append({'code': 'CSP_MISSING', 'msg': ''})

    # caching headers
    cache_ok = False
    cc = sec_headers.get('Cache-Control') or ''
    if cc and ('max-age' in cc or 'public' in cc):
        cache_ok = True
    if not cache_ok:
        issues.append({'code': 'CACHE_HEADERS_MISSING', 'msg': cc})

    # resource hints: preload fonts, preconnect/dns-prefetch
    if not re.search(r'<link[^>]+rel=["\']preload["\'][^>]*as=["\']font["\']', html, re.I):
        issues.append({'code': 'FONT_PRELOAD_MISSING', 'msg': ''})
    if not re.search(r'<link[^>]+rel=["\']preconnect|dns-prefetch["\']', html, re.I):
        issues.append({'code': 'RESOURCE_HINTS_MISSING', 'msg': ''})

    # accessibility: images missing alt or empty alt
    imgs = re.findall(r'<img\b[^>]*>', html, re.I)
    missing_alt = 0
    for im in imgs:
        if not re.search(r'\balt=\s*["\']', im, re.I):
            missing_alt += 1
        else:
            m = re.search(r'\balt=\s*["\']([^"\']*)["\']', im, re.I)
            if m and m.group(1).strip() == '':
                missing_alt += 1
    if missing_alt:
        issues.append({'code': 'IMAGES_MISSING_ALT', 'msg': f'{missing_alt} images'})

    # JSON-LD coverage heuristics
    expected = None
    p = urlparse(url).path
    if '/shop/product/' in p:
        expected = 'product'
    elif p.startswith('/blog/'):
        expected = 'article'
    elif p.startswith('/shop') or p == '/' or p.startswith('/category'):
        expected = 'breadcrumb'

    scripts = re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.I | re.S)
    parsed_ok = True
    parsed_objs = []
    for block in scripts:
        txt = block.strip()
        if not txt:
            continue
        try:
            obj = json.loads(txt)
            parsed_objs.append(obj)
        except Exception:
            parsed_ok = False
    if expected and not parsed_ok:
        issues.append({'code': 'JSONLD_PARSE_EXT', 'msg': ''})
    # if expected product, check product present
    if expected == 'product':
        found = False
        for obj in parsed_objs:
            typ = (obj.get('@type') or '').lower() if isinstance(obj, dict) else ''
            if 'product' in typ:
                found = True
        if not found:
            issues.append({'code': 'JSONLD_PRODUCT_MISSING', 'msg': ''})
    if expected == 'article':
        found = False
        for obj in parsed_objs:
            typ = (obj.get('@type') or '').lower() if isinstance(obj, dict) else ''
            if 'article' in typ or 'blogposting' in typ or 'newsarticle' in typ:
                found = True
        if not found:
            issues.append({'code': 'JSONLD_ARTICLE_MISSING', 'msg': ''})

    return issues


print('Running extended audit across sitemap URLs...')
for url in locs:
    EXT_COUNTS['total'] += 1
    time.sleep(RATE_DELAY)
    # Prefer using local BASE mapping to avoid DNS issues for hostnames like 'http://accountinox/...'
    parsed = urlparse(url)
    fetch_url = BASE + parsed.path
    if parsed.query:
        fetch_url += '?' + parsed.query
    try:
        r = requests.get(fetch_url, timeout=30, allow_redirects=True)
    except Exception as e:
        EXT_FAILURES.append({'url': url, 'errors': [{'code': 'HTTP_ERROR_EXT', 'msg': str(e)}]})
        EXT_COUNTS['issues'] += 1
        continue
    html = r.text
    ex_issues = check_page_extended(url, html, r)
    if ex_issues:
        EXT_FAILURES.append({'url': url, 'errors': ex_issues})
        EXT_COUNTS['issues'] += 1

ext_summary = {'counts': EXT_COUNTS, 'failures': EXT_FAILURES}
with open('seo_full_audit_summary.json', 'w', encoding='utf-8') as fh:
    json.dump(ext_summary, fh, indent=2, ensure_ascii=False)

print('Extended audit done. total=', EXT_COUNTS['total'], 'issues=', EXT_COUNTS['issues'])
print('Extended summary written to seo_full_audit_summary.json')
