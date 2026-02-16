import pytest
from django.urls import reverse
from django.conf import settings

from apps.accounts import sms_providers


@pytest.mark.django_db
def test_send_otp_with_ippanel(monkeypatch, client):
    # Configure settings to use ippanel provider
    monkeypatch.setattr(settings, 'SITE_SMS_PROVIDER', 'ippanel', raising=False)
    monkeypatch.setattr(settings, 'IPPANEL_API_KEY', 'fake-api-key', raising=False)

    # Mock urllib.request.urlopen used inside IPPanelProvider.send_sms
    class DummyResp:
        def __init__(self):
            self._code = 200

        def getcode(self):
            return self._code

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(sms_providers.urllib.request, 'urlopen', lambda req, timeout=10: DummyResp())

    url = reverse('accounts:send_otp')
    resp = client.post(url, {'phone': '09120000000'})
    assert resp.status_code == 200
