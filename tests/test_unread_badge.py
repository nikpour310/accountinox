import pytest
from django.test import Client
from django.urls import reverse
from django.contrib.auth.models import User
from apps.support.models import ChatSession, ChatMessage


@pytest.mark.django_db
def test_unread_count_in_operator_dashboard():
    """Test that unread count is shown per session in operator dashboard"""
    operator = User.objects.create_user(
        username='operator', password='oppass123', is_staff=True
    )
    user = User.objects.create_user(
        username='testuser', password='testpass123'
    )
    
    # Create a session with unread message from user
    session = ChatSession.objects.create(user=user, subject='Test')
    msg1 = ChatMessage.objects.create(
        session=session, name='User', message='Hello', is_from_user=True, read=False
    )
    msg2 = ChatMessage.objects.create(
        session=session, name='User', message='How are you?', is_from_user=True, read=False
    )
    
    # Operator views dashboard (without selecting session)
    client = Client()
    client.login(username='operator', password='oppass123')
    resp = client.get(reverse('support:operator_dashboard'))
    
    assert resp.status_code == 200
    # Check that context has active_sessions with unread_count annotation
    assert 'active_sessions' in resp.context
    sessions_in_context = list(resp.context['active_sessions'])
    assert len(sessions_in_context) >= 1
    assert sessions_in_context[0].unread_count == 2  # Two unread messages


@pytest.mark.django_db
def test_messages_marked_read_when_operator_views_session():
    """Test that messages are marked as read when operator views a session"""
    operator = User.objects.create_user(
        username='operator2', password='oppass123', is_staff=True
    )
    user = User.objects.create_user(
        username='testuser2', password='testpass123'
    )
    
    # Create session with unread messages
    session = ChatSession.objects.create(user=user, subject='Support Ticket')
    ChatMessage.objects.create(
        session=session, name='User', message='Help!', is_from_user=True, read=False
    )
    
    # Verify message is unread
    assert ChatMessage.objects.filter(session=session, read=False).count() == 1
    
    # Operator opens the dedicated session route
    client = Client()
    client.login(username='operator2', password='oppass123')
    resp = client.get(reverse('support:operator_session', args=[session.id]))
    
    assert resp.status_code == 200
    
    # Verify message is now marked as read
    assert ChatMessage.objects.filter(session=session, read=False).count() == 0
    msg = ChatMessage.objects.get(session=session)
    assert msg.read is True


@pytest.mark.django_db
def test_total_unread_count():
    """Test that total unread count is displayed in dashboard header"""
    operator = User.objects.create_user(
        username='operator3', password='oppass123', is_staff=True
    )
    user = User.objects.create_user(
        username='testuser3', password='testpass123'
    )
    
    # Create sessions with unread messages
    session1 = ChatSession.objects.create(user=user, subject='Issue 1')
    ChatMessage.objects.create(
        session=session1, name='User1', message='Problem 1', is_from_user=True, read=False
    )
    
    session2 = ChatSession.objects.create(
        user_name='anon_user', subject='Issue 2'
    )
    ChatMessage.objects.create(
        session=session2, name='AnonUser', message='Problem 2', is_from_user=True, read=False
    )
    
    # Verify total unread count
    assert ChatMessage.objects.filter(read=False, is_from_user=True).count() == 2
    
    # Operator views dashboard
    client = Client()
    client.login(username='operator3', password='oppass123')
    resp = client.get(reverse('support:operator_dashboard'))
    
    assert resp.status_code == 200
    assert resp.context['unread_count'] == 2


@pytest.mark.django_db
def test_total_unread_count_ignores_closed_sessions():
    """Unread badge should include only active sessions."""
    operator = User.objects.create_user(
        username='operator_closed', password='oppass123', is_staff=True
    )
    user = User.objects.create_user(
        username='testuser_closed', password='testpass123'
    )

    active_session = ChatSession.objects.create(user=user, subject='Active Issue', is_active=True)
    closed_session = ChatSession.objects.create(user=user, subject='Closed Issue', is_active=False)
    ChatMessage.objects.create(
        session=active_session, name='User', message='Active unread', is_from_user=True, read=False
    )
    ChatMessage.objects.create(
        session=closed_session, name='User', message='Closed unread', is_from_user=True, read=False
    )

    client = Client()
    client.login(username='operator_closed', password='oppass123')
    resp = client.get(reverse('support:operator_dashboard'))

    assert resp.status_code == 200
    assert resp.context['unread_count'] == 1


@pytest.mark.django_db
def test_operator_message_not_counted_as_unread():
    """Test that messages from operator are not counted as unread"""
    operator = User.objects.create_user(
        username='operator4', password='oppass123', is_staff=True
    )
    user = User.objects.create_user(
        username='testuser4', password='testpass123'
    )
    
    session = ChatSession.objects.create(user=user, subject='Chat')
    
    # User sends message (unread)
    ChatMessage.objects.create(
        session=session, name='User', message='Hi', is_from_user=True, read=False
    )
    
    # Operator replies (should not be counted as unread item)
    ChatMessage.objects.create(
        session=session, name='Operator', message='Hi there', 
        is_from_user=False, user=operator, read=False
    )
    
    # Only user messages (is_from_user=True) count towards unread
    unread = ChatMessage.objects.filter(read=False, is_from_user=True).count()
    assert unread == 1
