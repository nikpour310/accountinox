import time

import pytest
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import Client, override_settings
from django.urls import reverse


@pytest.mark.django_db
@override_settings(
    SESSION_IDLE_TIMEOUT_USER_SECONDS=120,
    SESSION_IDLE_TIMEOUT_STAFF_SECONDS=60,
)
def test_regular_user_is_logged_out_after_idle_timeout():
    user = User.objects.create_user(
        username='idle_user',
        email='idle_user@example.com',
        password='pass123456',
    )
    client = Client()
    client.force_login(user)

    session = client.session
    session['core_idle_last_activity_ts'] = int(time.time()) - 500
    session.save()

    response = client.get(reverse('core:landing'))
    assert response.status_code == 200
    assert '_auth_user_id' not in client.session
    flash_messages = [str(msg) for msg in get_messages(response.wsgi_request)]
    assert any('از حساب خود خارج شدید' in text for text in flash_messages)


@pytest.mark.django_db
@override_settings(
    SESSION_IDLE_TIMEOUT_USER_SECONDS=1200,
    SESSION_IDLE_TIMEOUT_STAFF_SECONDS=120,
)
def test_staff_timeout_is_shorter_than_regular_user_timeout():
    staff = User.objects.create_user(
        username='idle_staff',
        email='idle_staff@example.com',
        password='pass123456',
        is_staff=True,
        is_superuser=True,
    )
    regular = User.objects.create_user(
        username='idle_regular',
        email='idle_regular@example.com',
        password='pass123456',
    )

    stale_ts = int(time.time()) - 300

    staff_client = Client()
    staff_client.force_login(staff)
    staff_session = staff_client.session
    staff_session['core_idle_last_activity_ts'] = stale_ts
    staff_session.save()
    staff_resp = staff_client.get(reverse('core:landing'))
    assert staff_resp.status_code == 200
    assert '_auth_user_id' not in staff_client.session
    staff_flash_messages = [str(msg) for msg in get_messages(staff_resp.wsgi_request)]
    assert any('نشست مدیریتی شما' in text for text in staff_flash_messages)

    regular_client = Client()
    regular_client.force_login(regular)
    regular_session = regular_client.session
    regular_session['core_idle_last_activity_ts'] = stale_ts
    regular_session.save()
    regular_resp = regular_client.get(reverse('core:landing'))
    assert regular_resp.status_code == 200
    assert '_auth_user_id' in regular_client.session


@pytest.mark.django_db
def test_timeout_reason_is_shown_as_one_time_message():
    client = Client()
    session = client.session
    session['core_idle_timeout_reason'] = 'user'
    session.save()

    response = client.get(reverse('core:landing'))
    assert response.status_code == 200

    flash_messages = [str(msg) for msg in get_messages(response.wsgi_request)]
    assert any('به دلیل عدم فعالیت' in text for text in flash_messages)
    assert 'core_idle_timeout_reason' not in client.session
