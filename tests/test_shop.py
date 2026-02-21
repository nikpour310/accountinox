import pytest
from django.urls import reverse
from apps.shop.models import CartItem, OrderItem, Product


@pytest.mark.django_db
def test_product_list_view(client):
    resp = client.get(reverse('shop:product_list'))
    assert resp.status_code == 200


def test_plaintext_customer_password_fields_removed():
    order_item_fields = {field.name for field in OrderItem._meta.get_fields()}
    cart_item_fields = {field.name for field in CartItem._meta.get_fields()}
    assert 'customer_password' not in order_item_fields
    assert 'customer_password' not in cart_item_fields
