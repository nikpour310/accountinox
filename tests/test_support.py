"""Tests for support chat and operator workflow."""
import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.core.models import SiteSettings
from apps.support.models import ChatMessage, ChatSession, SupportAuditLog, SupportContact


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

    def test_support_index_lists_sessions_with_professional_statuses(self):
        self.client.login(username='testuser', password='testpass123')
        waiting_session = ChatSession.objects.create(user=self.user, user_name='customer', is_active=True)
        answered_session = ChatSession.objects.create(user=self.user, user_name='customer', is_active=True)
        closed_session = ChatSession.objects.create(user=self.user, user_name='customer', is_active=False)
        ChatMessage.objects.create(
            session=waiting_session,
            name='Customer',
            message='Need help',
            is_from_user=True,
        )
        ChatMessage.objects.create(
            session=answered_session,
            name='Operator',
            message='Sure, done',
            is_from_user=False,
        )

        response = self.client.get(reverse('support:chat'))
        assert response.status_code == 200
        sessions = response.context['session_list']
        labels = {s.id: s.status_label for s in sessions}
        assert labels[waiting_session.id] == 'در انتظار پاسخ'
        assert labels[answered_session.id] == 'پاسخ داده شده'
        assert labels[closed_session.id] == 'بسته'

    def test_support_index_supports_status_filter_and_query(self):
        self.client.login(username='testuser', password='testpass123')
        waiting_session = ChatSession.objects.create(user=self.user, user_name='customer', is_active=True)
        answered_session = ChatSession.objects.create(user=self.user, user_name='customer', is_active=True)
        ChatMessage.objects.create(
            session=waiting_session,
            name='Customer',
            message='Need help',
            is_from_user=True,
        )
        ChatMessage.objects.create(
            session=answered_session,
            name='Operator',
            message='Sure, done',
            is_from_user=False,
        )

        filtered = self.client.get(reverse('support:chat'), {'status': 'waiting'})
        assert filtered.status_code == 200
        filtered_ids = [s.id for s in filtered.context['session_list']]
        assert waiting_session.id in filtered_ids
        assert answered_session.id not in filtered_ids

        searched = self.client.get(reverse('support:chat'), {'status': 'all', 'q': str(answered_session.id)})
        assert searched.status_code == 200
        searched_ids = [s.id for s in searched.context['session_list']]
        assert searched_ids == [answered_session.id]

    def test_support_index_shows_ticket_action_feedback(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('support:chat'), {'ticket_action': 'closed'})
        assert response.status_code == 200
        assert response.context['ticket_action_message'] == 'گفتگو با موفقیت بسته شد.'

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
        contact = SupportContact.objects.create(name='Anon User', phone='09123334444')
        session = ChatSession.objects.create(contact=contact, user_name='anon', user_phone=contact.phone, subject='Test')
        client_session = self.client.session
        client_session['support_contact_id'] = contact.id
        client_session['support_session_id'] = session.id
        client_session['support_session_token'] = session.public_token
        client_session.save()
        response = self.client.post(
            reverse('support:send_message'),
            {'session_id': session.id, 'message': 'Hello support'},
        )
        assert response.status_code == 200
        data = response.json()
        assert data['ok'] is True
        assert ChatMessage.objects.filter(session=session, is_from_user=True).exists()

    def test_send_message_unauthenticated_requires_session_ownership(self):
        contact = SupportContact.objects.create(name='Victim', phone='09127778888')
        session = ChatSession.objects.create(contact=contact, user_name='victim', user_phone=contact.phone, subject='Secret')
        response = self.client.post(
            reverse('support:send_message'),
            {'session_id': session.id, 'message': 'intrusion'},
        )
        assert response.status_code == 403

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

    def test_send_message_after_close_returns_closed_error(self):
        contact = SupportContact.objects.create(name='Reuse User', phone='09125550000')
        closed_session = ChatSession.objects.create(
            contact=contact,
            user_name='Reuse User',
            user_phone='09125550000',
            subject='Old Session',
            is_active=False,
        )
        client_session = self.client.session
        client_session['support_contact_id'] = contact.id
        client_session['support_session_id'] = closed_session.id
        client_session['support_session_token'] = closed_session.public_token
        client_session.save()
        response = self.client.post(
            reverse('support:send_message'),
            {'session_id': closed_session.id, 'message': 'I am back'},
        )
        assert response.status_code == 400
        data = response.json()
        assert data['error'] == 'session is closed'
        assert data['session_closed'] is True
        assert ChatMessage.objects.filter(session=closed_session, is_from_user=True).count() == 0

    def test_send_message_missing_fields(self):
        response = self.client.post(reverse('support:send_message'), {'session_id': 999, 'message': ''})
        assert response.status_code in [400, 404]

    def test_get_messages_long_polling(self):
        contact = SupportContact.objects.create(name='Polling User', phone='09124445555')
        session = ChatSession.objects.create(contact=contact, user_name='test', user_phone=contact.phone, subject='Test')
        client_session = self.client.session
        client_session['support_contact_id'] = contact.id
        client_session['support_session_id'] = session.id
        client_session['support_session_token'] = session.public_token
        client_session.save()
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
        contact = SupportContact.objects.create(name='Polling User', phone='09126667777')
        session = ChatSession.objects.create(contact=contact, user_name='test', user_phone=contact.phone, subject='Test')
        client_session = self.client.session
        client_session['support_contact_id'] = contact.id
        client_session['support_session_id'] = session.id
        client_session['support_session_token'] = session.public_token
        client_session.save()
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

    def test_operator_dashboard_priority_sorts_critical_first(self):
        self.client.login(username='operator', password='oppass123')
        now = timezone.now()
        critical = ChatSession.objects.create(
            user_name='critical-user',
            subject='Critical',
            is_active=True,
            created_at=now - timezone.timedelta(hours=2),
        )
        fresh = ChatSession.objects.create(
            user_name='fresh-user',
            subject='Fresh',
            is_active=True,
            created_at=now - timezone.timedelta(minutes=10),
        )
        passive = ChatSession.objects.create(
            user_name='passive-user',
            subject='Passive',
            is_active=True,
            created_at=now - timezone.timedelta(minutes=30),
            assigned_to=self.staff_user,
        )
        ChatMessage.objects.create(
            session=critical,
            name='Customer',
            message='Old unread',
            is_from_user=True,
            read=False,
            created_at=now - timezone.timedelta(minutes=25),
        )
        ChatMessage.objects.create(
            session=fresh,
            name='Customer',
            message='Fresh unread',
            is_from_user=True,
            read=False,
            created_at=now - timezone.timedelta(minutes=2),
        )
        ChatMessage.objects.create(
            session=passive,
            name='Operator',
            message='No unread pending',
            is_from_user=False,
            read=True,
            created_at=now - timezone.timedelta(minutes=1),
        )

        response = self.client.get(reverse('support:operator_dashboard'))
        assert response.status_code == 200
        sessions = list(response.context['active_sessions'])
        assert sessions[0].id == critical.id
        assert sessions[0].priority_label == 'بحرانی'
        assert response.context['queue_summary']['critical'] >= 1
        assert response.context['queue_summary']['need_reply'] >= 2

    def test_operator_dashboard_filters_unread_sessions(self):
        self.client.login(username='operator', password='oppass123')
        unread_session = ChatSession.objects.create(user_name='need-reply', subject='Unread', is_active=True)
        done_session = ChatSession.objects.create(user_name='done', subject='Done', is_active=True)
        ChatMessage.objects.create(
            session=unread_session,
            name='Customer',
            message='please reply',
            is_from_user=True,
            read=False,
        )
        ChatMessage.objects.create(
            session=done_session,
            name='Operator',
            message='already answered',
            is_from_user=False,
            read=True,
        )

        response = self.client.get(reverse('support:operator_dashboard'), {'status': 'unread'})
        assert response.status_code == 200
        active_ids = [session.id for session in response.context['active_sessions']]
        assert unread_session.id in active_ids
        assert done_session.id not in active_ids
        assert response.context['queue_filter'] == 'unread'

    def test_operator_dashboard_uses_configurable_sla_thresholds(self):
        settings_obj = SiteSettings.load()
        settings_obj.support_sla_warning_seconds = 60
        settings_obj.support_sla_breach_seconds = 120
        settings_obj.save(update_fields=['support_sla_warning_seconds', 'support_sla_breach_seconds'])

        self.client.login(username='operator', password='oppass123')
        now = timezone.now()
        fresh = ChatSession.objects.create(user_name='fresh', subject='Fresh', is_active=True)
        warning = ChatSession.objects.create(user_name='warning', subject='Warning', is_active=True)
        breach = ChatSession.objects.create(user_name='breach', subject='Breach', is_active=True)
        ChatMessage.objects.create(
            session=fresh,
            name='Customer',
            message='fresh unread',
            is_from_user=True,
            read=False,
            created_at=now - timezone.timedelta(seconds=25),
        )
        ChatMessage.objects.create(
            session=warning,
            name='Customer',
            message='warning unread',
            is_from_user=True,
            read=False,
            created_at=now - timezone.timedelta(seconds=75),
        )
        ChatMessage.objects.create(
            session=breach,
            name='Customer',
            message='breach unread',
            is_from_user=True,
            read=False,
            created_at=now - timezone.timedelta(seconds=150),
        )

        response = self.client.get(reverse('support:operator_dashboard'))
        assert response.status_code == 200
        sessions_by_id = {session.id: session for session in response.context['active_sessions']}
        assert sessions_by_id[fresh.id].priority_rank == 2
        assert sessions_by_id[warning.id].priority_rank == 1
        assert sessions_by_id[breach.id].priority_rank == 0
        summary = response.context['queue_summary']
        assert summary['sla_warning_seconds'] == 60
        assert summary['sla_breach_seconds'] == 120
        assert summary['critical'] >= 1

        risk_response = self.client.get(reverse('support:operator_dashboard'), {'status': 'sla_risk'})
        assert risk_response.status_code == 200
        risk_ids = {session.id for session in risk_response.context['active_sessions']}
        assert fresh.id not in risk_ids
        assert warning.id in risk_ids
        assert breach.id in risk_ids

    def test_operator_dashboard_sla_thresholds_fallback_for_invalid_saved_values(self):
        settings_obj = SiteSettings.load()
        SiteSettings.objects.filter(pk=settings_obj.pk).update(
            support_sla_warning_seconds=5,
            support_sla_breach_seconds=5,
        )

        self.client.login(username='operator', password='oppass123')
        response = self.client.get(reverse('support:operator_dashboard'))
        assert response.status_code == 200
        summary = response.context['queue_summary']
        assert summary['sla_warning_seconds'] == 30
        assert summary['sla_breach_seconds'] == 60

    def test_site_settings_rejects_invalid_sla_relation_on_validation(self):
        settings_obj = SiteSettings.load()
        settings_obj.support_sla_warning_seconds = 120
        settings_obj.support_sla_breach_seconds = 60
        with pytest.raises(ValidationError):
            settings_obj.full_clean()

    def test_operator_dashboard_search_by_phone(self):
        self.client.login(username='operator', password='oppass123')
        target = ChatSession.objects.create(
            user_name='Ali Search',
            user_phone='09127770000',
            subject='Searchable',
            is_active=True,
        )
        ChatSession.objects.create(
            user_name='Other User',
            user_phone='09121110000',
            subject='Other',
            is_active=True,
        )

        response = self.client.get(reverse('support:operator_dashboard'), {'q': '09127770000', 'status': 'all'})
        assert response.status_code == 200
        result_ids = [session.id for session in response.context['active_sessions']]
        assert result_ids == [target.id]
        assert response.context['queue_query'] == '09127770000'

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

    def test_typing_update_and_status_for_user_owner(self):
        self.client.login(username='testuser', password='testpass123')
        session = ChatSession.objects.create(user=self.user, user_name='customer', is_active=True)

        update_resp = self.client.post(
            reverse('support:typing_update'),
            {'session_id': session.id, 'is_typing': '1'},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()['actor'] == 'user'
        assert update_resp.json()['is_typing'] is True

        status_resp = self.client.get(reverse('support:typing_status'), {'session_id': session.id})
        assert status_resp.status_code == 200
        status_payload = status_resp.json()
        assert status_payload['user_typing'] is True
        assert status_payload['operator_typing'] is False

        self.client.post(
            reverse('support:typing_update'),
            {'session_id': session.id, 'is_typing': '0'},
        )
        status_resp_after = self.client.get(reverse('support:typing_status'), {'session_id': session.id})
        assert status_resp_after.status_code == 200
        assert status_resp_after.json()['user_typing'] is False

    def test_typing_update_forbidden_for_non_owner(self):
        other = User.objects.create_user(
            username='typing_other',
            email='typing_other@example.com',
            password='pass123456',
        )
        session = ChatSession.objects.create(user=other, user_name='other', is_active=True)
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(
            reverse('support:typing_update'),
            {'session_id': session.id, 'is_typing': '1'},
        )
        assert response.status_code == 403

    def test_typing_update_and_status_for_operator(self):
        self.client.login(username='operator', password='oppass123')
        session = ChatSession.objects.create(user_name='customer', subject='Support', is_active=True)

        update_resp = self.client.post(
            reverse('support:typing_update'),
            {'session_id': session.id, 'is_typing': '1'},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()['actor'] == 'operator'
        assert update_resp.json()['is_typing'] is True

        status_resp = self.client.get(reverse('support:typing_status'), {'session_id': session.id})
        assert status_resp.status_code == 200
        assert status_resp.json()['operator_typing'] is True

        self.client.post(
            reverse('support:typing_update'),
            {'session_id': session.id, 'is_typing': '0'},
        )
        status_resp_after = self.client.get(reverse('support:typing_status'), {'session_id': session.id})
        assert status_resp_after.status_code == 200
        assert status_resp_after.json()['operator_typing'] is False

    def test_operator_session_context_has_quick_replies_and_audit_logs(self):
        self.client.login(username='operator', password='oppass123')
        session = ChatSession.objects.create(user_name='customer', subject='Support', is_active=True)
        SupportAuditLog.objects.create(
            staff=self.staff_user,
            action=SupportAuditLog.ACTION_SEND,
            session=session,
        )

        response = self.client.get(reverse('support:operator_session', args=[session.id]))
        assert response.status_code == 200
        assert 'quick_replies' in response.context
        assert len(response.context['quick_replies']) >= 1
        logs = list(response.context['audit_logs'])
        assert len(logs) >= 1
        assert hasattr(logs[0], 'action_label')
        assert hasattr(logs[0], 'actor_label')
        assert response.context['queue_summary']['sla_warning_seconds'] > 0
        assert response.context['queue_summary']['sla_breach_seconds'] > 0

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

    def test_user_can_close_own_session(self):
        self.client.login(username='testuser', password='testpass123')
        session = ChatSession.objects.create(user=self.user, user_name='customer', is_active=True)
        response = self.client.post(reverse('support:user_close_session', args=[session.id]))
        assert response.status_code == 302
        assert 'ticket_action=closed' in response.url
        session.refresh_from_db()
        assert session.is_active is False
        assert session.closed_at is not None
        assert session.closed_by_id == self.user.id

    def test_user_can_reopen_own_closed_session(self):
        self.client.login(username='testuser', password='testpass123')
        session = ChatSession.objects.create(
            user=self.user,
            user_name='customer',
            is_active=False,
            closed_at=timezone.now(),
            closed_by=self.user,
        )
        response = self.client.post(reverse('support:user_reopen_session', args=[session.id]))
        assert response.status_code == 302
        assert 'ticket_action=reopened' in response.url
        session.refresh_from_db()
        assert session.is_active is True
        assert session.closed_at is None
        assert session.closed_by is None

    def test_chat_room_context_contains_status_metadata(self):
        self.client.login(username='testuser', password='testpass123')
        session = ChatSession.objects.create(user=self.user, user_name='customer', is_active=True)
        ChatMessage.objects.create(
            session=session,
            name='Operator',
            message='Done',
            is_from_user=False,
        )
        self.client.session['support_session_id'] = session.id
        self.client.session.save()
        response = self.client.get(reverse('support:chat_room'))
        assert response.status_code == 200
        rendered_session = response.context['session']
        assert rendered_session.status_label == 'پاسخ داده شده'
        assert rendered_session.status_badge_class == 'bg-emerald-50 text-emerald-700'

    def test_user_cannot_close_other_user_session(self):
        other = User.objects.create_user(
            username='other_user',
            email='other@example.com',
            password='otherpass123',
        )
        session = ChatSession.objects.create(user=other, user_name='other', is_active=True)
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('support:user_close_session', args=[session.id]))
        assert response.status_code == 403
        session.refresh_from_db()
        assert session.is_active is True

    def test_user_open_session_sets_active_session_state(self):
        self.client.login(username='testuser', password='testpass123')
        session = ChatSession.objects.create(user=self.user, user_name='customer', is_active=True)
        response = self.client.get(reverse('support:user_open_session', args=[session.id]))
        assert response.status_code == 302
        assert response.url == reverse('support:chat_room')
        assert int(self.client.session.get('support_session_id')) == session.id

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
