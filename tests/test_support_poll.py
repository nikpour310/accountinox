"""
Tests for poll endpoint and notifications
"""
import pytest
from django.test import Client
from django.urls import reverse
from apps.support.models import ChatSession, ChatMessage
from apps.core.models import SiteSettings
from django.core import mail


@pytest.mark.django_db
def test_poll_endpoint_returns_new_messages():
    client = Client()
    session = ChatSession.objects.create(user_name='tester', subject='Hi')
    # create a message
    msg = ChatMessage.objects.create(session=session, name='Tester', message='Hello', is_from_user=True)

    resp = client.get(reverse('support:poll_messages'), {'thread_id': session.id, 'since': 0, 'timeout': 1})
    assert resp.status_code == 200
    data = resp.json()
    assert 'messages' in data
    assert len(data['messages']) >= 1
    assert data['messages'][0]['message'] == 'Hello'


@pytest.mark.django_db
def test_poll_endpoint_invalid_numeric_params_do_not_500():
    client = Client()
    session = ChatSession.objects.create(user_name='tester', subject='Hi')
    ChatMessage.objects.create(session=session, name='Tester', message='Hello', is_from_user=True)

    resp = client.get(
        reverse('support:poll_messages'),
        {'thread_id': session.id, 'since': 'bad', 'timeout': '999999'},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert 'messages' in data


@pytest.mark.django_db
def test_get_messages_invalid_numeric_params_do_not_500():
    client = Client()
    session = ChatSession.objects.create(user_name='tester', subject='Hi')
    ChatMessage.objects.create(session=session, name='Tester', message='Hello', is_from_user=True)

    resp = client.get(
        reverse('support:get_messages'),
        {'session_id': session.id, 'last_id': 'bad', 'timeout': '999999'},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert 'messages' in data


@pytest.mark.django_db
def test_support_email_notification_sent():
    client = Client()
    settings = SiteSettings.load()
    settings.support_email_notifications_enabled = True
    settings.support_notify_email = 'ops@example.com'
    settings.save()

    session = ChatSession.objects.create(user_name='anon', subject='Help')
    resp = client.post(reverse('support:send_message'), {'session_id': session.id, 'message': 'Need help'})
    assert resp.status_code == 200
    # Email backend in tests is locmem - check outbox
    assert len(mail.outbox) >= 1
    assert settings.support_notify_email in mail.outbox[0].to
