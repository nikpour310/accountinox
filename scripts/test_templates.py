import os
import sys
from pathlib import Path
proj_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(proj_root))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.test import Client

pages = ['/', '/accounts/login/', '/shop/', '/support/']
client = Client()

ok = True
print('Running template rendering checks...')
for page in pages:
    try:
        resp = client.get(page)
    except Exception as e:
        print(f'{page}: request failed: {e}')
        ok = False
        continue
    status = resp.status_code
    print('\nPAGE', page, 'status', status)
    if status != 200:
        ok = False
    vary = resp.get('Vary')
    print('  Vary header:', vary)
    content = resp.content.decode('utf-8', errors='ignore')
    has_picture = '<picture' in content
    has_webp = '.webp' in content
    print('  contains <picture>:', has_picture, 'contains .webp:', has_webp)

print('\nDone.')
if not ok:
    sys.exit(2)

