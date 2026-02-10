import pytest
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import PhoneOTP


@pytest.mark.django_db
def test_otp_expiry(client):
    phone = '09330000000'
    url = reverse('accounts:send_otp')
    client.post(url, {'phone': phone})
    otp = PhoneOTP.objects.get(phone=phone)
    # simulate expiry
    otp.created_at = timezone.now() - timezone.timedelta(seconds=9999)
    otp.save()
    verify_url = reverse('accounts:verify_otp')
    resp = client.post(verify_url, {'phone': phone, 'code': '000000'})
    assert resp.status_code == 400 and 'expired' in resp.json().get('error', '')


@pytest.mark.django_db
def test_otp_cooldown_and_max_attempts(client):
    phone = '09330000001'
    send_url = reverse('accounts:send_otp')
    client.post(send_url, {'phone': phone})
    # immediate resend should be blocked (cooldown default 60)
    resp = client.post(send_url, {'phone': phone})
    assert resp.status_code in (429, 400)

    # test max attempts
    otp = PhoneOTP.objects.get(phone=phone)
    verify_url = reverse('accounts:verify_otp')
    for i in range(6):
        r = client.post(verify_url, {'phone': phone, 'code': 'wrong'})
    # after max attempts should be locked
    r = client.post(verify_url, {'phone': phone, 'code': 'wrong'})
    assert r.status_code in (403, 400)
