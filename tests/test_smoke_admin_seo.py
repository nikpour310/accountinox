import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.urls import NoReverseMatch, reverse

from apps.accounts.models import PhoneOTP
from apps.blog.models import Post
from apps.blog.models import PostFAQ
from apps.shop.models import Category, Order, Product, TransactionLog
from apps.support.models import ChatSession, SupportContact
from apps.support.models import SupportRating


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username='admin_smoke',
        email='admin_smoke@example.com',
        password='pass123456',
    )


@pytest.mark.django_db
def test_admin_blog_changelist_renders_with_post_rows(client, admin_user):
    Post.objects.create(
        title='Smoke Blog Post',
        slug='smoke-blog-post',
        content='post content',
        published=True,
    )
    client.force_login(admin_user)

    response = client.get(reverse('admin:blog_post_changelist'))
    assert response.status_code == 200


@pytest.mark.django_db
def test_admin_change_form_pages_render_without_template_errors(client, admin_user):
    client.force_login(admin_user)

    blog_add = client.get(reverse('admin:blog_post_add'))
    email_add = client.get(reverse('admin:account_emailaddress_add'))
    assert blog_add.status_code == 200
    assert email_add.status_code == 200


@pytest.mark.django_db
def test_admin_support_chatsession_changelist_renders_without_operator(client, admin_user):
    contact = SupportContact.objects.create(name='Smoke Contact', phone='09121234567')
    ChatSession.objects.create(
        contact=contact,
        user_name='Smoke Contact',
        user_phone='09121234567',
        subject='Smoke Session',
        is_active=True,
    )
    client.force_login(admin_user)

    response = client.get(reverse('admin:support_chatsession_changelist'))
    assert response.status_code == 200


@pytest.mark.django_db
def test_admin_phoneotp_changelist_renders(client, admin_user):
    client.force_login(admin_user)
    response = client.get(reverse('admin:accounts_phoneotp_changelist'))
    assert response.status_code == 200


@pytest.mark.django_db
def test_admin_model_changelist_and_add_pages_do_not_500(client, admin_user):
    client.force_login(admin_user)
    checked = 0
    for model in admin.site._registry.keys():
        app_label = model._meta.app_label
        model_name = model._meta.model_name
        for suffix in ('changelist', 'add'):
            url_name = f'admin:{app_label}_{model_name}_{suffix}'
            try:
                url = reverse(url_name)
            except NoReverseMatch:
                continue
            checked += 1
            response = client.get(url)
            assert response.status_code < 500, f'{url_name} returned {response.status_code}'
    assert checked > 0


@pytest.mark.django_db
def test_admin_core_model_changelist_add_change_pages(client, admin_user):
    client.force_login(admin_user)

    category = Category.objects.create(name='Admin Smoke Cat', slug='admin-smoke-cat')
    product = Product.objects.create(
        category=category,
        title='Admin Smoke Product',
        slug='admin-smoke-product',
        price='49.00',
    )
    order = Order.objects.create(user=admin_user, total='49.00', paid=False)
    tx = TransactionLog.objects.create(order=order, provider='zarinpal', success=False, payload={})
    post = Post.objects.create(title='Admin Smoke Post', slug='admin-smoke-post', content='x', published=False)
    faq = PostFAQ.objects.create(post=post, question='q', answer='a')
    contact = SupportContact.objects.create(name='Admin Smoke Contact', phone='09127778888')
    session = ChatSession.objects.create(
        contact=contact,
        user_name='Admin Smoke Contact',
        user_phone='09127778888',
        subject='Admin Session',
        is_active=False,
    )
    rating = SupportRating.objects.create(session=session, agent=admin_user, score=5, reason='')
    otp = PhoneOTP.objects.create(phone='09125551111')

    targets = [
        ('admin:support_chatsession_changelist', None, 200),
        ('admin:support_chatsession_add', None, 200),
        ('admin:support_chatsession_change', [session.id], 200),
        ('admin:support_supportcontact_changelist', None, 200),
        ('admin:support_supportcontact_add', None, 200),
        ('admin:support_supportcontact_change', [contact.id], 200),
        ('admin:support_supportrating_changelist', None, 200),
        ('admin:support_supportrating_add', None, 200),
        ('admin:support_supportrating_change', [rating.id], 200),
        ('admin:shop_order_changelist', None, 200),
        ('admin:shop_order_add', None, 200),
        ('admin:shop_order_change', [order.id], 200),
        ('admin:shop_transactionlog_changelist', None, 200),
        ('admin:shop_transactionlog_add', None, 200),
        ('admin:shop_transactionlog_change', [tx.id], 200),
        ('admin:shop_product_changelist', None, 200),
        ('admin:shop_product_add', None, 200),
        ('admin:shop_product_change', [product.id], 200),
        ('admin:blog_post_changelist', None, 200),
        ('admin:blog_post_add', None, 200),
        ('admin:blog_post_change', [post.id], 200),
        ('admin:blog_postfaq_changelist', None, 200),
        ('admin:blog_postfaq_add', None, 200),
        ('admin:blog_postfaq_change', [faq.id], 200),
        ('admin:accounts_phoneotp_changelist', None, 200),
        ('admin:accounts_phoneotp_add', None, 200),
        ('admin:accounts_phoneotp_change', [otp.id], 200),
    ]

    for url_name, args, expected in targets:
        url = reverse(url_name, args=args or [])
        response = client.get(url)
        assert response.status_code == expected, f'{url_name} expected {expected} got {response.status_code}'

    try:
        email_add_url = reverse('admin:account_emailaddress_add')
    except NoReverseMatch:
        email_add_url = None
    if email_add_url:
        email_add_resp = client.get(email_add_url)
        assert email_add_resp.status_code == 200


@pytest.mark.django_db
def test_smoke_seo_and_service_worker_endpoints(client):
    robots = client.get(reverse('robots_txt'))
    sitemap = client.get(reverse('sitemap'))
    sw = client.get(reverse('service_worker'))
    health = client.get(reverse('healthcheck'))

    assert robots.status_code == 200
    assert sitemap.status_code == 200
    assert sw.status_code == 200
    assert health.status_code == 200
    assert 'Sitemap:' in robots.content.decode('utf-8')
    assert sw['Service-Worker-Allowed'] == '/'


@pytest.mark.django_db
def test_footer_legal_links_resolve(client):
    landing = client.get(reverse('core:landing'))
    terms = client.get(reverse('core:terms'))
    privacy = client.get(reverse('core:privacy'))
    contact = client.get(reverse('core:contact'))

    assert landing.status_code == 200
    assert terms.status_code == 200
    assert privacy.status_code == 200
    assert contact.status_code == 200

    landing_html = landing.content.decode('utf-8')
    assert reverse('core:terms') in landing_html
    assert reverse('core:privacy') in landing_html
    assert reverse('core:contact') in landing_html
