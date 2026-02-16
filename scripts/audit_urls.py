#!/usr/bin/env python
"""Comprehensive URL audit - tests all pages in the project."""
import os, sys, django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()

# Create a superuser for admin testing if not exists
if not User.objects.filter(username='testadmin').exists():
    User.objects.create_superuser('testadmin', 'admin@test.com', 'testpass123')

c = Client()
c.login(username='testadmin', password='testpass123')

url_groups = {
    'PUBLIC': [
        ('/', 'Landing'),
        ('/terms/', 'Terms'),
        ('/privacy/', 'Privacy'),
        ('/contact/', 'Contact'),
        ('/healthz/', 'Healthcheck'),
        ('/robots.txt', 'Robots'),
        ('/sitemap.xml', 'Sitemap'),
        ('/blog/', 'Blog List'),
        ('/shop/', 'Product List'),
        ('/shop/services/', 'Service List'),
        ('/shop/cart/', 'Cart'),
        ('/support/', 'Support Index'),
    ],
    'AUTH (allauth)': [
        ('/accounts/login/', 'Login Page'),
        ('/accounts/signup/', 'Signup Page'),
        ('/accounts/password/reset/', 'Password Reset'),
    ],
    'USER PANEL': [
        ('/accounts/', 'Dashboard'),
        ('/accounts/orders/', 'Order List'),
        ('/accounts/profile/', 'Profile'),
        ('/accounts/addresses/', 'Address Book'),
    ],
    'ADMIN': [
        ('/admin/', 'Admin Dashboard'),
        ('/admin/auth/user/', 'Admin Users'),
        ('/admin/auth/group/', 'Admin Groups'),
        ('/admin/blog/post/', 'Admin Blog Posts'),
        ('/admin/shop/category/', 'Admin Shop Categories'),
        ('/admin/shop/product/', 'Admin Products'),
        ('/admin/shop/accountitem/', 'Admin Account Items'),
        ('/admin/shop/order/', 'Admin Orders'),
        ('/admin/shop/transactionlog/', 'Admin Transactions'),
        ('/admin/shop/service/', 'Admin Services'),
        ('/admin/accounts/profile/', 'Admin Profiles'),
        ('/admin/accounts/phoneotp/', 'Admin Phone OTPs'),
        ('/admin/accounts/orderaddress/', 'Admin Addresses'),
        ('/admin/core/herobanner/', 'Admin Hero Banners'),
        ('/admin/core/sitesettings/', 'Admin Site Settings'),
        ('/admin/core/globalfaq/', 'Admin Global FAQs'),
        ('/admin/core/truststat/', 'Admin Trust Stats'),
        ('/admin/core/featurecard/', 'Admin Feature Cards'),
        ('/admin/core/footerlink/', 'Admin Footer Links'),
        ('/admin/support/chatsession/', 'Admin Chat Sessions'),
        ('/admin/support/chatmessage/', 'Admin Chat Messages'),
        ('/admin/support/supportrating/', 'Admin Support Ratings'),
        ('/admin/support/supportpushsubscription/', 'Admin Push Subs'),
        ('/admin/support/supportcontact/', 'Admin Support Contacts'),
        ('/admin/support/supportoperatorpresence/', 'Admin Operator Presence'),
        ('/admin/support/supportauditlog/', 'Admin Audit Log'),
    ],
    'SUPPORT': [
        ('/support/chat/', 'Chat Room'),
        ('/support/operator/', 'Operator Dashboard'),
    ],
}

errors = []
total = 0
ok_count = 0

for group_name, urls in url_groups.items():
    print(f"\n{'=' * 60}")
    print(f"  {group_name}")
    print(f"{'=' * 60}")
    for url, name in urls:
        total += 1
        try:
            resp = c.get(url, follow=True)
            status = resp.status_code
            if status == 200:
                ok_count += 1
                print(f"  OK   {name:30s} {url}")
            else:
                errors.append((url, name, f'HTTP {status}'))
                print(f"  FAIL {name:30s} {url} -> {status}")
        except Exception as e:
            err_msg = str(e)[:80]
            errors.append((url, name, err_msg))
            print(f"  ERR  {name:30s} {url} -> {err_msg}")

print(f"\n{'=' * 60}")
print(f"  SUMMARY: {ok_count}/{total} OK, {len(errors)} failures")
print(f"{'=' * 60}")
if errors:
    print("\nFailed URLs:")
    for url, name, err in errors:
        print(f"  - {name} ({url}): {err}")
