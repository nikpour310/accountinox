import os
import sys
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, proj_root)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
print('RUNNING MANUAL WALKTHROUGH')
from django.test import Client

email='trkcoder@gmail.com'
password='Zxc@123567'

c = Client()
login_url = '/accounts/login/'
resp = c.get(login_url)
print('GET login page status', resp.status_code)
# POST login
post = c.post(login_url, {'login': email, 'password': password}, follow=True)
print('POST login final status', post.status_code)
# Check if logged in by accessing account dashboard
for url in ['/account/', '/accounts/']:
    r = c.get(url)
    print('GET', url, 'status', r.status_code)
    if r.status_code==200:
        content = r.content.decode('utf-8', errors='ignore')
        if email in content:
            print('  appears to be logged in (email found in page)')
        else:
            # check for logout link
            if 'خروج' in content or 'log out' in content.lower():
                print('  appears to be logged in (logout text found)')
            else:
                print('  login may have failed or page does not show user')

# Basic accessibility hint: check for alt attributes on images on homepage
home = c.get('/')
html = home.content.decode('utf-8', errors='ignore')
missing_alt_count = 0
import re
for m in re.finditer(r"<img\s+([^>]+)>", html, flags=re.IGNORECASE):
    tag = m.group(1)
    if 'alt=' not in tag.lower():
        missing_alt_count += 1
print('Homepage images without alt (count)', missing_alt_count)

print('\nManual walkthrough done')
