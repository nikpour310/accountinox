import os, sys, django
sys.path.append(os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.test import Client
c = Client()
try:
    print("Requesting / ...")
    r = c.get('/')
    print(f"Status: {r.status_code}")
    if r.status_code != 200:
        print(r.content.decode('utf-8')[:2000]) # Print first 2k chars
except Exception as e:
    import traceback
    traceback.print_exc()
