"""
Pytest configuration and fixtures
"""
import os
import django
from django.conf import settings

# Set test FERNET_KEY if not already set
if not getattr(settings, 'FERNET_KEY', None):
    from cryptography.fernet import Fernet
    test_key = Fernet.generate_key().decode()
    settings.FERNET_KEY = test_key
    os.environ['FERNET_KEY'] = test_key
