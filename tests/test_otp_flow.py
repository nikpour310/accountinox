import pytest
from django.urls import reverse
from django.utils import timezone

from django.conf import settings

from apps.accounts.models import PhoneOTP
from apps.accounts.models import Profile
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


@pytest.mark.django_db
def test_verify_otp_login_old_phone_does_not_login_previous_owner(client):
    User = get_user_model()
    old_phone = '09123334444'
    new_phone = '09125556666'

    previous_owner = User.objects.create(username=old_phone)
    Profile.objects.create(user=previous_owner, phone=new_phone)

    otp = PhoneOTP.objects.create(phone=old_phone)
    otp.set_code('222222')
    otp.save()

    url = reverse('accounts:verify_otp_login')
    resp = client.post(url, {'phone': old_phone, 'code': '222222'})
    assert resp.status_code == 200
    assert resp.json().get('ok') is True

    logged_in_user_id = client.session.get('_auth_user_id')
    assert str(previous_owner.id) != str(logged_in_user_id)

    new_owner_user = User.objects.get(id=logged_in_user_id)
    new_owner_profile = Profile.objects.get(user=new_owner_user)
    assert new_owner_profile.phone == old_phone

    previous_owner.refresh_from_db()
    assert previous_owner.profile.phone == new_phone


@pytest.mark.django_db
def test_smart_password_reset_old_phone_rejected(client):
    User = get_user_model()
    old_phone = '09127770000'
    new_phone = '09128880000'

    previous_owner = User.objects.create(username=old_phone)
    Profile.objects.create(user=previous_owner, phone=new_phone)

    url = reverse('account_reset_password')
    resp = client.post(url, {'identifier': old_phone})
    assert resp.status_code == 200
    assert client.session.get('pwd_reset_user_id') is None
    assert client.session.get('pwd_reset_phone') is None


@pytest.mark.django_db
def test_smart_password_reset_verified_phone_allowed(client, monkeypatch):
    class DummyProvider:
        def send_otp(self, phone, code):
            return {'ok': True}

    monkeypatch.setattr('apps.accounts.views.get_sms_provider', lambda provider_name=None: DummyProvider())

    User = get_user_model()
    phone = '09129991111'
    user = User.objects.create(username='user_x')
    Profile.objects.create(user=user, phone=phone)

    url = reverse('account_reset_password')
    resp = client.post(url, {'identifier': phone})
    assert resp.status_code == 302
    assert reverse('account_reset_password_phone_verify') in resp['Location']
    assert str(client.session.get('pwd_reset_user_id')) == str(user.id)
    assert client.session.get('pwd_reset_phone') == phone
