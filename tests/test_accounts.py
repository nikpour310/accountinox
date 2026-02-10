import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_send_otp_client(client):
    url = reverse('accounts:send_otp')
    resp = client.post(url, {'phone': '09120000000'})
    assert resp.status_code in (200, 302)
