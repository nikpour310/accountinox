import json

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.support import views as support_views
from apps.support.models import (
    ChatSession,
    SupportOperatorPresence,
    SupportPushSubscription,
)


@pytest.mark.django_db
def test_staff_can_subscribe_push_endpoint():
    client = Client()
    staff = User.objects.create_user(
        username='push_staff',
        password='pushpass123',
        is_staff=True,
        is_superuser=True,
    )
    assert client.login(username='push_staff', password='pushpass123')

    payload = {
        'endpoint': 'https://push.example/subscriptions/1',
        'keys': {
            'p256dh': 'test-p256dh-key',
            'auth': 'test-auth-key',
        },
    }
    response = client.post(
        reverse('support:push_subscribe'),
        data=json.dumps(payload),
        content_type='application/json',
    )

    assert response.status_code == 200
    data = response.json()
    assert data['ok'] is True
    assert data['active_subs'] >= 1
    assert data['active_subs_user'] == 1
    subscription = SupportPushSubscription.objects.get(user=staff, endpoint=payload['endpoint'])
    assert subscription.p256dh == payload['keys']['p256dh']
    assert subscription.auth == payload['keys']['auth']
    assert subscription.is_active is True


@pytest.mark.django_db
def test_staff_can_unsubscribe_push_endpoint():
    client = Client()
    staff = User.objects.create_user(
        username='push_staff_unsub',
        password='pushpass123',
        is_staff=True,
        is_superuser=True,
    )
    assert client.login(username='push_staff_unsub', password='pushpass123')

    subscription = SupportPushSubscription.objects.create(
        user=staff,
        endpoint='https://push.example/subscriptions/2',
        p256dh='key-2',
        auth='auth-2',
        is_active=True,
    )

    response = client.post(
        reverse('support:push_unsubscribe'),
        data=json.dumps({'endpoint': subscription.endpoint}),
        content_type='application/json',
    )

    assert response.status_code == 200
    data = response.json()
    assert data['ok'] is True
    assert data['updated'] == 1
    subscription.refresh_from_db()
    assert subscription.is_active is False


@pytest.mark.django_db
def test_user_message_dispatches_push_only_for_online_staff(settings, monkeypatch):
    settings.SUPPORT_PUSH_ENABLED = True
    settings.VAPID_PUBLIC_KEY = 'test-public-key'
    settings.VAPID_PRIVATE_KEY = 'test-private-key'
    settings.VAPID_SUBJECT = 'mailto:ops@example.com'

    client = Client()
    user = User.objects.create_user(username='chat_user', password='userpass123')
    online_staff = User.objects.create_user(
        username='chat_staff_online',
        password='staffpass123',
        is_staff=True,
        is_superuser=True,
    )
    offline_staff = User.objects.create_user(
        username='chat_staff_offline',
        password='staffpass123',
        is_staff=True,
        is_superuser=True,
    )

    session = ChatSession.objects.create(user=user, subject='Need Support')
    assert client.login(username='chat_user', password='userpass123')
    SupportOperatorPresence.objects.create(user=online_staff, last_seen_at=timezone.now())
    SupportPushSubscription.objects.create(
        user=online_staff,
        endpoint='https://push.example/subscriptions/online',
        p256dh='key-online',
        auth='auth-online',
        is_active=True,
    )
    SupportPushSubscription.objects.create(
        user=offline_staff,
        endpoint='https://push.example/subscriptions/offline',
        p256dh='key-offline',
        auth='auth-offline',
        is_active=True,
    )

    push_calls = []

    def fake_webpush(**kwargs):
        push_calls.append(kwargs)

    monkeypatch.setattr(support_views, 'webpush', fake_webpush)

    response = client.post(
        reverse('support:send_message'),
        data={
            'session_id': session.id,
            'message': 'new support message',
        },
    )
    assert response.status_code == 200
    assert len(push_calls) == 1
    assert 'online' in push_calls[0]['subscription_info']['endpoint']

    pushed_payload = json.loads(push_calls[0]['data'])
    assert pushed_payload['title']
    assert str(session.id) in pushed_payload['url']
    assert pushed_payload['thread_id'] == session.id
    assert 'message_id' in pushed_payload


@pytest.mark.django_db
def test_push_not_sent_when_operator_active_on_same_thread(settings, monkeypatch):
    settings.SUPPORT_PUSH_ENABLED = True
    settings.VAPID_PUBLIC_KEY = 'test-public-key'
    settings.VAPID_PRIVATE_KEY = 'test-private-key'
    settings.VAPID_SUBJECT = 'mailto:ops@example.com'

    client = Client()
    user = User.objects.create_user(username='chat_user_same', password='userpass123')
    staff = User.objects.create_user(
        username='chat_staff_same',
        password='staffpass123',
        is_staff=True,
        is_superuser=True,
    )
    session = ChatSession.objects.create(user=user, subject='Need Support')
    assert client.login(username='chat_user_same', password='userpass123')
    SupportOperatorPresence.objects.create(
        user=staff,
        last_seen_at=timezone.now(),
        active_session=session,
    )
    SupportPushSubscription.objects.create(
        user=staff,
        endpoint='https://push.example/subscriptions/same',
        p256dh='key-same',
        auth='auth-same',
        is_active=True,
    )

    push_calls = []

    def fake_webpush(**kwargs):
        push_calls.append(kwargs)

    monkeypatch.setattr(support_views, 'webpush', fake_webpush)

    response = client.post(
        reverse('support:send_message'),
        data={'session_id': session.id, 'message': 'message same thread'},
    )
    assert response.status_code == 200
    assert push_calls == []


@pytest.mark.django_db
def test_push_debug_endpoint_for_staff(settings):
    settings.SUPPORT_PUSH_ENABLED = True
    settings.VAPID_PUBLIC_KEY = 'test-public-key'

    client = Client()
    staff = User.objects.create_user(
        username='push_debug_staff',
        password='pushpass123',
        is_staff=True,
        is_superuser=True,
    )
    SupportPushSubscription.objects.create(
        user=staff,
        endpoint='https://push.example/subscriptions/debug',
        p256dh='debug-key',
        auth='debug-auth',
        is_active=True,
    )
    SupportOperatorPresence.objects.create(user=staff, last_seen_at=timezone.now())
    assert client.login(username='push_debug_staff', password='pushpass123')

    response = client.get(reverse('support:push_debug'))
    assert response.status_code == 200
    data = response.json()
    assert data['enabled'] is True
    assert data['vapid_public_present'] is True
    assert data['subs_count'] == 1
    assert data['active_subs'] == 1
    assert data['online_staff_count'] == 1
    assert 'last_error' in data


@pytest.mark.django_db
def test_webpush_410_disables_subscription(settings, monkeypatch):
    settings.SUPPORT_PUSH_ENABLED = True
    settings.VAPID_PUBLIC_KEY = 'test-public-key'
    settings.VAPID_PRIVATE_KEY = 'test-private-key'
    settings.VAPID_SUBJECT = 'mailto:ops@example.com'

    client = Client()
    user = User.objects.create_user(username='chat_user_410', password='userpass123')
    staff = User.objects.create_user(
        username='chat_staff_410',
        password='staffpass123',
        is_staff=True,
        is_superuser=True,
    )
    session = ChatSession.objects.create(user=user, subject='Need Support 410')
    assert client.login(username='chat_user_410', password='userpass123')
    SupportOperatorPresence.objects.create(user=staff, last_seen_at=timezone.now())
    subscription = SupportPushSubscription.objects.create(
        user=staff,
        endpoint='https://push.example/subscriptions/expired',
        p256dh='key-expired',
        auth='auth-expired',
        is_active=True,
    )

    class FakeWebPushException(Exception):
        def __init__(self, status_code):
            super().__init__('gone')
            self.response = type('Resp', (), {'status_code': status_code})()

    monkeypatch.setattr(support_views, 'WebPushException', FakeWebPushException)

    def fake_webpush_raise(**kwargs):
        raise FakeWebPushException(410)

    monkeypatch.setattr(support_views, 'webpush', fake_webpush_raise)

    response = client.post(
        reverse('support:send_message'),
        data={
            'session_id': session.id,
            'message': 'expired subscription message',
        },
    )
    assert response.status_code == 200
    subscription.refresh_from_db()
    assert subscription.is_active is False
