import pytest
from django.test import Client
from django.urls import reverse
from apps.core.models import SiteSettings


@pytest.mark.django_db
def test_support_page_shows_telegram_links():
    client = Client()
    settings = SiteSettings.load()
    settings.telegram_admin_url = 'https://t.me/test_admin'
    settings.telegram_channel_url = 'https://t.me/test_channel'
    settings.telegram_support_label = 'تلگرام پشتیبانی'
    settings.save()

    resp = client.get(reverse('support:chat'))
    assert resp.status_code == 200
    content = resp.content.decode('utf-8')
    assert 'https://t.me/test_admin' in content
    assert 'https://t.me/test_channel' in content
    assert 'تلگرام پشتیبانی' in content
