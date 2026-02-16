import os
import sys
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, proj_root)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.test import Client
from django.conf import settings
import re

pages = ['/', '/accounts/login/', '/shop/', '/support/']
client = Client()
print('ANALYZE SITE: headers and images')

for page in pages:
    try:
        resp = client.get(page)
    except Exception as e:
        print(f'{page}: request failed: {e}')
        continue
    status = resp.status_code
    # headers
    headers = {}
    if hasattr(resp, 'headers'):
        headers = {k: resp.headers.get(k) for k in ('X-Frame-Options','X-Content-Type-Options','Referrer-Policy','Content-Security-Policy','Strict-Transport-Security')}
    else:
        # fallback to _headers dict
        h = getattr(resp, '_headers', {})
        for key in ('x-frame-options','x-content-type-options','referrer-policy','content-security-policy','strict-transport-security'):
            v = h.get(key)
            headers[key] = v[1] if v else None
    print('\nPAGE', page, 'status', status)
    for k, val in headers.items():
        print('  header', k, ':', val)
    # cookies attributes (secure/httpOnly)
    cookies = resp.cookies
    if cookies:
        for name, cookie in cookies.items():
            print('  cookie', name, 'secure=', getattr(cookie, 'secure', False), 'httponly=', getattr(cookie, 'httponly', False))
    # images
    html = resp.content.decode('utf-8', errors='ignore')
    imgs = []
    for m in re.finditer(r'<img\s+[^>]*src=["\']([^"\']+)["\']', html, flags=re.IGNORECASE):
        src = m.group(1)
        imgs.append(src)
    print('  images found:', len(imgs))
    large = []
    for src in imgs:
        path = None
        if src.startswith('/static/'):
            rel = src.split('/static/', 1)[1]
            p1 = os.path.join(settings.BASE_DIR, 'static', rel)
            p2 = os.path.join(settings.BASE_DIR, 'staticfiles', rel)
            if os.path.exists(p1):
                path = p1
            elif os.path.exists(p2):
                path = p2
        elif src.startswith('/media/'):
            rel = src.split('/media/', 1)[1]
            p = os.path.join(settings.MEDIA_ROOT, rel)
            if os.path.exists(p):
                path = p
        elif src.startswith('http'):
            path = None
        else:
            # relative path - try static
            p = os.path.join(settings.BASE_DIR, 'static', src.lstrip('/'))
            if os.path.exists(p):
                path = p
        if path and os.path.exists(path):
            size = os.path.getsize(path)
            if size > 200 * 1024:
                large.append((src, size))
    print('  large images (>200KB):', len(large))
    for s, sz in large[:10]:
        print('   ', s, '->', round(sz/1024,1), 'KB')

print('\nAnalysis complete')
