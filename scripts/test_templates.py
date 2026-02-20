import os
import sys
from pathlib import Path


def main() -> int:
    proj_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(proj_root))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

    import django
    from django.test import Client

    django.setup()

    pages = ['/', '/accounts/login/', '/shop/', '/support/']
    client = Client()

    ok = True
    print('Running template rendering checks...')
    for page in pages:
        try:
            resp = client.get(page)
        except Exception as exc:
            print(f'{page}: request failed: {exc}')
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
    return 0 if ok else 2


if __name__ == '__main__':
    raise SystemExit(main())

