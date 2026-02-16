import os
import sys
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, proj_root)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.test import Client

pages = ['/', '/accounts/login/', '/shop/', '/support/']
user_agents = {
    'desktop': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
    'mobile': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1'
}

c = Client()

for page in pages:
    print('\n== PAGE:', page)
    for label, ua in user_agents.items():
        resp = c.get(page, HTTP_USER_AGENT=ua)
        content = resp.content.decode('utf-8', errors='ignore')[:8000]
        has_viewport = '<meta name="viewport"' in content.lower() or '<meta name=\'viewport\'' in content.lower()
        title = ''
        if '<title>' in content.lower():
            try:
                start = content.lower().index('<title>') + 7
                end = content.lower().index('</title>', start)
                title = content[start:end].strip()
            except Exception:
                title = ''
        print(f"  {label}: status={resp.status_code}, title='{title}', has_viewport={has_viewport}, len={len(content)}")

print('\nScan complete')
