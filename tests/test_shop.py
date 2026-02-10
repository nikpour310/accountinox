import pytest
from django.urls import reverse
from apps.shop.models import Product


@pytest.mark.django_db
def test_product_list_view(client):
    resp = client.get(reverse('shop:product_list'))
    assert resp.status_code == 200
