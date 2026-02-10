import os
import shutil

BASE = os.path.dirname(os.path.dirname(__file__))
TEMPLATES = [
    'templates/landing.html',
    'templates/shop/product_list.html',
    'templates/shop/product_detail.html',
    'templates/shop/cart.html',
    'templates/shop/checkout.html',
    'templates/accounts/login.html',
    'templates/account/login.html',
    'templates/accounts/profile.html',
    'templates/accounts/addresses.html',
    'templates/support/chat.html',
    'templates/support/operator_dashboard.html',
]
OUT = os.path.join(BASE, 'screenshots')
os.makedirs(OUT, exist_ok=True)

for t in TEMPLATES:
    src = os.path.join(BASE, t)
    name = t.replace('templates/', '').replace('/', '_')
    dst = os.path.join(OUT, name)
    if os.path.exists(src):
        shutil.copyfile(src, dst)
        print('Copied', src, '->', dst)
    else:
        with open(dst, 'w', encoding='utf-8') as f:
            f.write(f'<!-- Missing template: {t} -->\n')
        print('Missing', src, '-> wrote placeholder', dst)

print('Saved template snapshots to', OUT)
