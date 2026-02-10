import json

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.support.models import ChatSession, SupportAuditLog


@pytest.mark.django_db
def test_push_subscribe_creates_audit_log():
    client = Client()
    staff = User.objects.create_user(
        username='audit_staff_sub',
        password='pass123',
        is_staff=True,
        is_superuser=True,
    )
    assert client.login(username='audit_staff_sub', password='pass123')

    payload = {
        'endpoint': 'https://push.example/subscriptions/audit',
        'keys': {'p256dh': 'key-audit', 'auth': 'auth-audit'},
    }
    response = client.post(
        reverse('support:push_subscribe'),
        data=json.dumps(payload),
        content_type='application/json',
    )
    assert response.status_code == 200
    assert SupportAuditLog.objects.filter(
        staff=staff,
        action=SupportAuditLog.ACTION_SUBSCRIBE,
    ).exists()


@pytest.mark.django_db
def test_operator_send_creates_audit_log():
    client = Client()
    staff = User.objects.create_user(
        username='audit_staff_send',
        password='pass123',
        is_staff=True,
        is_superuser=True,
    )
    session = ChatSession.objects.create(user_name='customer', subject='Audit Send')
    assert client.login(username='audit_staff_send', password='pass123')

    response = client.post(
        reverse('support:operator_send_message'),
        {'session_id': session.id, 'message': 'operator reply'},
        HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        HTTP_ACCEPT='application/json',
    )
    assert response.status_code == 200
    assert SupportAuditLog.objects.filter(
        staff=staff,
        action=SupportAuditLog.ACTION_SEND,
        session=session,
    ).exists()


@pytest.mark.django_db
def test_close_session_creates_audit_log():
    client = Client()
    staff = User.objects.create_user(
        username='audit_staff_close',
        password='pass123',
        is_staff=True,
        is_superuser=True,
    )
    session = ChatSession.objects.create(user_name='customer', subject='Audit Close', is_active=True)
    assert client.login(username='audit_staff_close', password='pass123')

    response = client.get(reverse('support:close_session', args=[session.id]))
    assert response.status_code in [302, 200]
    assert SupportAuditLog.objects.filter(
        staff=staff,
        action=SupportAuditLog.ACTION_CLOSE,
        session=session,
    ).exists()
