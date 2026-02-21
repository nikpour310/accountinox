import pytest
from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured

from apps.shop.models import AccountItem, Product
from config.settings import _validate_fernet_key_or_raise


@pytest.mark.django_db
def test_account_item_encryption_is_active(settings):
    settings.FERNET_KEY = Fernet.generate_key().decode()
    product = Product.objects.create(title='Enc Product', slug='enc-product', price='10.00')
    item = AccountItem.objects.create(product=product)

    item.set_plain('enc-user@example.com', 'SuperSecret!123', 'sensitive notes')

    assert isinstance(item.username_encrypted, (bytes, bytearray))
    assert isinstance(item.password_encrypted, (bytes, bytearray))
    assert b'enc-user@example.com' not in item.username_encrypted
    assert b'SuperSecret!123' not in item.password_encrypted
    assert item.get_plain()['username'] == 'enc-user@example.com'


@pytest.mark.django_db
def test_account_item_set_plain_fails_when_fernet_key_missing(settings):
    settings.FERNET_KEY = ''
    product = Product.objects.create(title='Enc Product 2', slug='enc-product-2', price='10.00')
    item = AccountItem.objects.create(product=product)

    with pytest.raises(RuntimeError):
        item.set_plain('user', 'pass')


def test_settings_fernet_validator_rejects_invalid_key():
    with pytest.raises(ImproperlyConfigured):
        _validate_fernet_key_or_raise('not-a-valid-fernet-key')


def test_settings_fernet_validator_accepts_valid_key():
    key = Fernet.generate_key().decode()
    _validate_fernet_key_or_raise(key)
