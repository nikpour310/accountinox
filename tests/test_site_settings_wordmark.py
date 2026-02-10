import pytest
from django.urls import reverse

from apps.core.models import SiteSettings


@pytest.mark.django_db
def test_wordmark_fa_is_rendered_in_layout_brand_slots(client):
    settings_obj = SiteSettings.load()
    settings_obj.site_name = 'Accountinox Default'
    settings_obj.brand_wordmark_fa = 'اکانتینوکس ویژه'
    settings_obj.save()

    response = client.get(reverse('core:landing'))
    assert response.status_code == 200

    content = response.content.decode('utf-8')
    assert content.count('اکانتینوکس ویژه') >= 3


@pytest.mark.django_db
def test_blank_wordmark_falls_back_to_site_name(client):
    settings_obj = SiteSettings.load()
    settings_obj.site_name = 'Accountinox Fallback'
    settings_obj.brand_wordmark_fa = ''
    settings_obj.save()

    response = client.get(reverse('core:landing'))
    assert response.status_code == 200

    content = response.content.decode('utf-8')
    assert content.count('Accountinox Fallback') >= 3
