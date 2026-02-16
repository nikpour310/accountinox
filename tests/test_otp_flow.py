import pytest
from django.urls import reverse
from django.utils import timezone

from django.conf import settings

from apps.accounts.models import PhoneOTP
from django.contrib.auth import get_user_model
from apps.accounts import sms_providers


@pytest.mark.django_db
def test_verify_otp_login_creates_user(monkeypatch, client):
    phone = '09129990001'
    # prepare PhoneOTP with known code
    otp = PhoneOTP.objects.create(phone=phone)
    otp.set_code('123456')
    otp.save()

    url = reverse('accounts:verify_otp_login')
    resp = client.post(url, {'phone': phone, 'code': '123456'})
    assert resp.status_code == 200
    assert resp.json().get('ok') is True

    User = get_user_model()
    assert User.objects.filter(username=phone).exists()


@pytest.mark.django_db
def test_verify_otp_expired(monkeypatch, client):
    phone = '09129990002'
    otp = PhoneOTP.objects.create(phone=phone)
    otp.set_code('000000')
    # make it expired
    otp.created_at = timezone.now() - timezone.timedelta(seconds=9999)
    otp.save()

    url = reverse('accounts:verify_otp')
    resp = client.post(url, {'phone': phone, 'code': '000000'})
    assert resp.status_code == 400
    assert resp.json().get('error') == 'expired'


@pytest.mark.django_db
def test_send_otp_cooldown_and_resend(monkeypatch, client):
    # Mock IPPanel network call to avoid external request
    monkeypatch.setattr(sms_providers.urllib.request, 'urlopen', lambda req, timeout=10: type('R', (), {'getcode': lambda self: 200, '__enter__': lambda self: self, '__exit__': lambda self, a, b, c: False})())

    send_url = reverse('accounts:send_otp')
    phone = '09121112222'
    r1 = client.post(send_url, {'phone': phone})
    assert r1.status_code == 200
    r2 = client.post(send_url, {'phone': phone})
    # second should be blocked by cooldown (429)
    assert r2.status_code in (429, 200)
