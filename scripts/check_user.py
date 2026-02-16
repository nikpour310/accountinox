import os
import sys
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, proj_root)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.contrib.auth import get_user_model
User=get_user_model()
email='trkcoder@gmail.com'
password='Zxc@123567'
try:
    u=User.objects.filter(email=email).first()
    if not u:
        print('NO_USER')
    else:
        print('USER_FOUND', u.get_username(), u.email)
        print('check_password', u.check_password(password))
except Exception as e:
    import traceback
    traceback.print_exc()
