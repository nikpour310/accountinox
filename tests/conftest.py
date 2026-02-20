"""
Pytest configuration and fixtures
"""
import os
import pytest
import django
from django.conf import settings
from django.core.cache import cache

# Set test FERNET_KEY if not already set
if not getattr(settings, 'FERNET_KEY', None):
    from cryptography.fernet import Fernet
    test_key = Fernet.generate_key().decode()
    settings.FERNET_KEY = test_key
    os.environ['FERNET_KEY'] = test_key


@pytest.fixture(autouse=True)
def clear_cache_per_test():
    """
    Prevent cross-test leakage for rate-limit counters and cached singletons.
    """
    cache.clear()
    yield
    cache.clear()
