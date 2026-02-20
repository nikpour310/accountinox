import pytest
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.blog.models import Post
from apps.shop.models import Category, Order, Product, TransactionLog
from apps.support.models import ChatMessage, ChatSession, SupportContact


@pytest.fixture
def route_seed(db):
    category = Category.objects.create(name='Smoke Routes', slug='smoke-routes')
    product = Product.objects.create(
        category=category,
        title='Smoke Product',
        slug='smoke-product',
        price='99.99',
    )
    post = Post.objects.create(
        title='Smoke Blog',
        slug='smoke-blog',
        content='smoke blog content',
        published=True,
    )
    contact = SupportContact.objects.create(name='Smoke Contact', phone='09121112222')
    session = ChatSession.objects.create(
        contact=contact,
        user_name='Smoke Contact',
        user_phone='09121112222',
        subject='Smoke Session',
        is_active=True,
    )
    return {
        'product': product,
        'post': post,
        'session': session,
    }


@pytest.fixture
def support_staff(db):
    return User.objects.create_user(
        username='support_staff',
        email='support_staff@example.com',
        password='pass123456',
        is_staff=True,
        is_superuser=True,
    )


@pytest.mark.django_db
def test_public_shop_blog_support_and_seo_routes_smoke(client, route_seed):
    routes = [
        (reverse('core:landing'), 200),
        (reverse('core:terms'), 200),
        (reverse('core:privacy'), 200),
        (reverse('core:cookies'), 200),
        (reverse('core:contact'), 200),
        (reverse('shop:product_list'), 200),
        (reverse('shop:product_detail', args=[route_seed['product'].slug]), 200),
        (reverse('shop:cart'), 200),
        (reverse('shop:checkout'), 200),
        (reverse('blog:post_list'), 200),
        (reverse('blog:post_detail', args=[route_seed['post'].slug]), 200),
        (reverse('support:chat'), 200),
        (reverse('support:chat_room'), 302),  # no user session yet
        (reverse('support:start_chat'), 405),  # POST-only endpoint
        (reverse('support:send_message'), 405),  # POST-only endpoint
        (reverse('robots_txt'), 200),
        (reverse('sitemap'), 200),
        (reverse('service_worker'), 200),
        (reverse('healthcheck'), 200),
    ]
    for path, expected_status in routes:
        response = client.get(path)
        assert response.status_code == expected_status, f'{path} expected {expected_status} got {response.status_code}'


@pytest.mark.django_db
def test_support_rate_route_smoke_requires_owner_or_session_state(client, route_seed):
    operator = User.objects.create_user(
        username='rate_operator',
        email='rate_operator@example.com',
        password='pass123456',
        is_staff=True,
    )
    closed_session = ChatSession.objects.create(
        contact=route_seed['session'].contact,
        user_name='Closed Session User',
        user_phone='09121112222',
        subject='Closed Session',
        is_active=False,
        assigned_to=operator,
        operator=operator,
        closed_by=operator,
    )

    # No prior session state: should not pass ownership gate.
    response = client.get(reverse('support:rate_session', args=[closed_session.id]))
    assert response.status_code == 302

    # With valid session state for the same contact: should be accessible.
    session_state = client.session
    session_state['support_contact_id'] = closed_session.contact_id
    session_state['support_session_id'] = closed_session.id
    session_state.save()
    allowed_response = client.get(reverse('support:rate_session', args=[closed_session.id]))
    assert allowed_response.status_code == 200


@pytest.mark.django_db
@patch('apps.shop.views.get_payment_provider')
def test_checkout_post_smoke_creates_transaction(mock_get_provider, client, route_seed):
    provider_mock = MagicMock()
    provider_mock.initiate_payment.return_value = (
        True,
        {'reference': 'SMOKE-REF', 'payment_url': 'https://gateway.example.test/pay'},
    )
    mock_get_provider.return_value = provider_mock

    response = client.post(
        reverse('shop:checkout'),
        {'product_id': route_seed['product'].id, 'gateway': 'zarinpal'},
    )
    assert response.status_code == 302
    assert TransactionLog.objects.filter(provider='zarinpal', payload__reference='SMOKE-REF').exists()


@pytest.mark.django_db
def test_account_dashboard_requires_login(client):
    routes = [
        reverse('accounts:dashboard'),
        reverse('account_panel:dashboard'),
        reverse('accounts:orders'),
        reverse('accounts:profile'),
        reverse('accounts:addresses'),
    ]
    for path in routes:
        response = client.get(path)
        assert response.status_code == 302


@pytest.mark.django_db
def test_order_detail_requires_owner(client):
    owner = User.objects.create_user(username='order_owner', email='owner@example.com', password='pass123456')
    stranger = User.objects.create_user(
        username='order_stranger',
        email='stranger@example.com',
        password='pass123456',
    )
    order = Order.objects.create(user=owner, total='100.00', paid=True)

    client.force_login(stranger)
    response = client.get(reverse('accounts:order_detail', args=[order.id]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_operator_routes_smoke(client, route_seed, support_staff):
    # Anonymous should be redirected by staff_member_required.
    response = client.get(reverse('support:operator_dashboard'))
    assert response.status_code == 302

    client.force_login(support_staff)
    session_id = route_seed['session'].id
    routes = [
        (reverse('support:operator_dashboard'), 200),
        (reverse('support:operator_session', args=[session_id]), 200),
        (reverse('support:operator_send_message'), 405),  # POST-only endpoint
        (reverse('support:operator_presence'), 200),
        (reverse('support:operator_unread_status'), 200),
        (reverse('support:close_session', args=[session_id]), 302),
    ]
    for path, expected_status in routes:
        response = client.get(path)
        assert response.status_code == expected_status, f'{path} expected {expected_status} got {response.status_code}'


@pytest.mark.django_db
def test_admin_routes_smoke(client, support_staff):
    client.force_login(support_staff)
    routes = [
        (reverse('admin:index'), 200),
        (reverse('admin:blog_post_changelist'), 200),
        (reverse('admin:shop_order_changelist'), 200),
        (reverse('admin:shop_transactionlog_changelist'), 200),
        (reverse('admin:support_chatsession_changelist'), 200),
        (reverse('admin:support_supportcontact_changelist'), 200),
        (reverse('admin:support_supportrating_changelist'), 200),
        (reverse('admin:accounts_phoneotp_changelist'), 200),
    ]
    for path, expected_status in routes:
        response = client.get(path)
        assert response.status_code == expected_status, f'{path} expected {expected_status} got {response.status_code}'


@pytest.mark.django_db
def test_support_start_chat_to_close_and_reopen_smoke():
    user_client = Client()
    operator_client = Client()
    operator = User.objects.create_superuser(
        username='support_flow_admin',
        email='support_flow_admin@example.com',
        password='pass123456',
    )

    start_resp = user_client.post(
        reverse('support:start_chat'),
        {'name': 'Flow User', 'phone': '09121117777'},
    )
    assert start_resp.status_code == 302

    session_id = user_client.session.get('support_session_id')
    assert session_id

    send_resp = user_client.post(
        reverse('support:send_message'),
        {'session_id': session_id, 'message': 'اولین پیام'},
    )
    assert send_resp.status_code == 200

    poll_resp = user_client.get(
        reverse('support:poll_messages'),
        {'session_id': session_id, 'since': 0, 'timeout': 1},
    )
    assert poll_resp.status_code == 200
    assert poll_resp.json()['messages']

    operator_client.force_login(operator)
    close_resp = operator_client.get(reverse('support:close_session', args=[session_id]))
    assert close_resp.status_code in (200, 302)

    old_session = ChatSession.objects.get(id=session_id)
    assert old_session.is_active is False
    assert old_session.closed_by_id == operator.id
    assert ChatMessage.objects.filter(session=old_session, is_from_user=True, read=False).count() == 0

    blocked_resp = user_client.post(
        reverse('support:send_message'),
        {'session_id': session_id, 'message': 'بعد از بستن دوباره پیام دادم'},
    )
    assert blocked_resp.status_code == 400
    assert blocked_resp.json().get('session_closed') is True

    reopen_resp = user_client.post(
        reverse('support:user_reopen_session', args=[session_id]),
        follow=True,
    )
    assert reopen_resp.status_code in (200, 302)

    reopened = ChatSession.objects.get(id=session_id)
    assert reopened.is_active is True
    assert reopened.contact_id == old_session.contact_id

    send_after_reopen = user_client.post(
        reverse('support:send_message'),
        {'session_id': session_id, 'message': 'بعد از بازکردن تیکت'},
    )
    assert send_after_reopen.status_code == 200
    assert ChatMessage.objects.filter(session=reopened, is_from_user=True, read=False).count() == 1


@pytest.mark.django_db
def test_poll_messages_reports_session_closed_flag():
    user_client = Client()
    operator_client = Client()
    operator = User.objects.create_superuser(
        username='support_poll_close_admin',
        email='support_poll_close_admin@example.com',
        password='pass123456',
    )

    start_resp = user_client.post(
        reverse('support:start_chat'),
        {'name': 'Poll User', 'phone': '09121118888'},
    )
    assert start_resp.status_code == 302

    session_id = user_client.session.get('support_session_id')
    assert session_id

    operator_client.force_login(operator)
    close_resp = operator_client.get(reverse('support:close_session', args=[session_id]))
    assert close_resp.status_code in (200, 302)

    poll_resp = user_client.get(
        reverse('support:poll_messages'),
        {'thread_id': session_id, 'since': 0, 'timeout': 1},
    )
    assert poll_resp.status_code == 200
    data = poll_resp.json()
    assert data['session_closed'] is True
    assert data['messages'] == []


@pytest.mark.django_db
@patch('apps.shop.views.get_payment_provider')
def test_checkout_and_callback_reference_mismatch_smoke(mock_get_provider, client, route_seed):
    provider_mock = MagicMock()
    provider_mock.initiate_payment.return_value = (
        True,
        {'reference': 'AUTH-RIGHT', 'payment_url': 'https://gateway.example.test/pay'},
    )
    provider_mock.verify_payment.return_value = (True, {'verified': True})
    mock_get_provider.return_value = provider_mock

    checkout_resp = client.post(
        reverse('shop:checkout'),
        {'product_id': route_seed['product'].id, 'gateway': 'zarinpal'},
    )
    assert checkout_resp.status_code == 302

    order = Order.objects.order_by('-id').first()
    assert order is not None

    callback_resp = client.get(
        reverse('shop:payment_callback', args=['zarinpal']),
        {'Status': '100', 'Authority': 'AUTH-WRONG', 'order_id': order.id},
    )
    assert callback_resp.status_code == 400

    order.refresh_from_db()
    assert order.paid is False

    tx = TransactionLog.objects.filter(order=order).order_by('-id').first()
    assert tx is not None
    assert tx.success is False
    mismatch = (tx.payload or {}).get('reference_mismatch', {})
    assert mismatch.get('expected') == 'AUTH-RIGHT'
    assert mismatch.get('received') == 'AUTH-WRONG'
