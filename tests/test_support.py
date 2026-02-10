"""Tests for support chat and operator workflow."""
import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.support.models import ChatMessage, ChatSession, SupportContact


@pytest.mark.django_db
class TestChatSupport:
    def setup_method(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
        )
        self.staff_user = User.objects.create_user(
            username='operator',
            email='operator@example.com',
            password='oppass123',
            is_staff=True,
            is_superuser=True,
        )

    def test_chat_index_renders_start_form_without_creating_session(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('support:chat'))
        assert response.status_code == 200
        assert ChatSession.objects.filter(user=self.user, is_active=True).count() == 0

    def test_start_chat_requires_name_and_phone(self):
        response = self.client.post(reverse('support:start_chat'), {'name': '', 'phone': ''})
        assert response.status_code == 400
        assert SupportContact.objects.count() == 0
        assert ChatSession.objects.count() == 0

    def test_start_chat_creates_contact_and_active_session(self):
        response = self.client.post(
            reverse('support:start_chat'),
            {'name': 'Ali Test', 'phone': '+989121234567'},
        )
        assert response.status_code == 302
        assert response.url == reverse('support:chat_room')

        contact = SupportContact.objects.get()
        assert contact.phone == '09121234567'
        session = ChatSession.objects.get(contact=contact, is_active=True)
        assert session.user_name == 'Ali Test'
        assert session.user_phone == '09121234567'

    def test_duplicate_phone_reuses_contact(self):
        self.client.post(reverse('support:start_chat'), {'name': 'First Name', 'phone': '09120001111'})
        response = self.client.post(
            reverse('support:start_chat'),
            {'name': 'Updated Name', 'phone': '+989120001111'},
        )
        assert response.status_code == 302
        assert SupportContact.objects.count() == 1
        contact = SupportContact.objects.get(phone='09120001111')
        assert contact.name == 'Updated Name'
        assert ChatSession.objects.filter(contact=contact, is_active=True).count() == 1

    def test_support_contact_model_normalizes_phone_on_save(self):
        contact = SupportContact.objects.create(name='Model Save', phone='09 12 000 2222')
        assert contact.phone == '09120002222'

    def test_send_message_unauthenticated(self):
        session = ChatSession.objects.create(user_name='anon', subject='Test')
        response = self.client.post(
            reverse('support:send_message'),
            {'session_id': session.id, 'message': 'Hello support'},
        )
        assert response.status_code == 200
        data = response.json()
        assert data['ok'] is True
        assert ChatMessage.objects.filter(session=session, is_from_user=True).exists()

    def test_send_message_authenticated(self):
        self.client.login(username='testuser', password='testpass123')
        session = ChatSession.objects.create(user=self.user, subject='Test')
        response = self.client.post(
            reverse('support:send_message'),
            {'session_id': session.id, 'message': 'Hello from user'},
        )
        assert response.status_code == 200
        msg = ChatMessage.objects.filter(session=session).first()
        assert msg is not None
        assert msg.user == self.user
        assert msg.message == 'Hello from user'

    def test_send_message_after_close_creates_new_active_session(self):
        contact = SupportContact.objects.create(name='Reuse User', phone='09125550000')
        closed_session = ChatSession.objects.create(
            contact=contact,
            user_name='Reuse User',
            user_phone='09125550000',
            subject='Old Session',
            is_active=False,
        )
        response = self.client.post(
            reverse('support:send_message'),
            {'session_id': closed_session.id, 'message': 'I am back'},
        )
        assert response.status_code == 200
        data = response.json()
        assert data['ok'] is True
        assert int(data['session_id']) != closed_session.id

        new_session = ChatSession.objects.get(id=data['session_id'])
        assert new_session.is_active is True
        assert new_session.contact_id == contact.id
        assert ChatMessage.objects.filter(
            session=new_session,
            is_from_user=True,
            read=False,
        ).count() == 1

    def test_send_message_missing_fields(self):
        response = self.client.post(reverse('support:send_message'), {'session_id': 999, 'message': ''})
        assert response.status_code in [400, 404]

    def test_get_messages_long_polling(self):
        session = ChatSession.objects.create(user_name='test', subject='Test')
        ChatMessage.objects.create(
            session=session,
            name='User',
            message='First message',
            is_from_user=True,
        )
        response = self.client.get(
            reverse('support:get_messages'),
            {'session_id': session.id, 'last_id': 0, 'timeout': 1},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data['messages']) > 0
        assert data['messages'][0]['message'] == 'First message'
        assert data['messages'][0]['is_from_user'] is True

    def test_get_messages_no_new_messages(self):
        session = ChatSession.objects.create(user_name='test', subject='Test')
        msg = ChatMessage.objects.create(
            session=session,
            name='User',
            message='Message',
            is_from_user=True,
        )
        response = self.client.get(
            reverse('support:get_messages'),
            {'session_id': session.id, 'last_id': msg.id, 'timeout': 1},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data['messages']) == 0

    def test_operator_dashboard_requires_staff(self):
        response = self.client.get(reverse('support:operator_dashboard'))
        assert response.status_code in [302, 403]

    def test_operator_can_view_dashboard(self):
        self.client.login(username='operator', password='oppass123')
        response = self.client.get(reverse('support:operator_dashboard'))
        assert response.status_code == 200

    def test_operator_send_message_form_redirects_to_session_view(self):
        self.client.login(username='operator', password='oppass123')
        session = ChatSession.objects.create(user_name='customer', subject='Support')
        response = self.client.post(
            reverse('support:operator_send_message'),
            {'session_id': session.id, 'message': 'We will help you'},
        )
        assert response.status_code == 302
        assert response.url == reverse('support:operator_session', args=[session.id])
        msg = ChatMessage.objects.filter(session=session, is_from_user=False).first()
        assert msg is not None
        assert msg.user == self.staff_user
        assert msg.message == 'We will help you'

    def test_operator_send_message_ajax_returns_json(self):
        self.client.login(username='operator', password='oppass123')
        session = ChatSession.objects.create(user_name='customer', subject='Support')
        response = self.client.post(
            reverse('support:operator_send_message'),
            {'session_id': session.id, 'message': 'We will help via ajax'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_ACCEPT='application/json',
        )
        assert response.status_code == 200
        data = response.json()
        assert data['ok'] is True
        assert data['message'] == 'We will help via ajax'
        assert data['is_from_user'] is False

    def test_operator_can_view_session_and_it_marks_unread_as_read(self):
        self.client.login(username='operator', password='oppass123')
        session = ChatSession.objects.create(user_name='customer', subject='Support')
        ChatMessage.objects.create(
            session=session,
            name='Customer',
            message='Need help',
            is_from_user=True,
            read=False,
        )
        response = self.client.get(reverse('support:operator_session', args=[session.id]))
        assert response.status_code == 200
        assert ChatMessage.objects.filter(session=session, is_from_user=True, read=False).count() == 0

    def test_operator_close_session(self):
        self.client.login(username='operator', password='oppass123')
        session = ChatSession.objects.create(user_name='customer', subject='Support', is_active=True)
        response = self.client.get(reverse('support:close_session', args=[session.id]))
        assert response.status_code in [302, 200]
        session.refresh_from_db()
        assert session.is_active is False
        assert session.closed_at is not None

    def test_operator_close_session_marks_unread_messages_read(self):
        self.client.login(username='operator', password='oppass123')
        session = ChatSession.objects.create(user_name='customer', subject='Support', is_active=True)
        ChatMessage.objects.create(
            session=session,
            name='Customer',
            message='Need help',
            is_from_user=True,
            read=False,
        )
        ChatMessage.objects.create(
            session=session,
            name='Customer',
            message='Still waiting',
            is_from_user=True,
            read=False,
        )
        response = self.client.get(reverse('support:close_session', args=[session.id]))
        assert response.status_code in [302, 200]
        assert ChatMessage.objects.filter(session=session, is_from_user=True, read=False).count() == 0

    def test_chat_session_model(self):
        session = ChatSession.objects.create(user=self.user, subject='Test Subject')
        assert session.is_active is True
        assert session.user == self.user
        session.close()
        assert session.is_active is False
        assert session.closed_at is not None

    def test_chat_message_model(self):
        session = ChatSession.objects.create(user_name='test')
        msg = ChatMessage.objects.create(
            session=session,
            name='Test User',
            message='Test message',
            is_from_user=True,
        )
        assert msg.session == session
        assert msg.is_from_user is True
        assert msg.read is False

        msg2 = ChatMessage.objects.create(
            session=session,
            user=self.staff_user,
            message='Response',
            is_from_user=False,
        )
        assert msg2.is_from_user is False
