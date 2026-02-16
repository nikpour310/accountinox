import os
import time
import socket
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

BASE = 'http://127.0.0.1:8000'
PATHS = [
    '/',
    '/shop/',
    '/cart/',
    '/shop/checkout/',
    '/accounts/login/',
    '/accounts/signup/',
    '/accounts/profile/',
    '/accounts/addresses/',
    '/support/chat/',
    '/support/operator/',
    '/support/operator/dashboard/',
]

OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'screenshots')
os.makedirs(OUT_DIR, exist_ok=True)

# Wait for server to be ready
def wait_for_server(timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = Request(BASE, headers={'User-Agent':'snapshot-bot'})
            with urlopen(req, timeout=2) as r:
                return True
        except Exception:
            time.sleep(0.5)
    return False

if not wait_for_server(15):
    print('Server not responding on', BASE)
    # proceed anyway; attempts will fail per-URL

for path in PATHS:
    url = BASE.rstrip('/') + path
    safe = path.strip('/').replace('/', '_') or 'index'
    out = os.path.join(OUT_DIR, f"{safe}.html")
    try:
        req = Request(url, headers={'User-Agent':'snapshot-bot'})
        with urlopen(req, timeout=10) as r:
            content = r.read()
            with open(out, 'wb') as f:
                f.write(content)
            print(url, '->', out, '(', r.getcode(), ')')
    except HTTPError as e:
        body = e.read() if hasattr(e, 'read') else b''
        with open(out, 'wb') as f:
            f.write(body)
        print(url, 'HTTPError', e.code, '->', out)
    except URLError as e:
        with open(out, 'w', encoding='utf-8') as f:
            f.write(f'Error: {e}\n')
        print(url, 'URLError', e, '->', out)
    except socket.timeout:
        with open(out, 'w', encoding='utf-8') as f:
            f.write('Error: timeout\n')
        print(url, 'timeout ->', out)

print('Snapshots saved to', OUT_DIR)
