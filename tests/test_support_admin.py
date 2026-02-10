import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.support.models import SupportContact


@pytest.mark.django_db
def test_support_contact_registered_in_admin():
    assert SupportContact in admin.site._registry


@pytest.mark.django_db
def test_support_contact_admin_search_smoke():
    superuser = User.objects.create_superuser(
        username='admin_support',
        email='admin_support@example.com',
        password='pass123456',
    )
    contact = SupportContact.objects.create(name='Ali Support', phone='09 12 345 6789')
    assert contact.phone == '09123456789'

    client = Client()
    client.force_login(superuser)

    response = client.get(reverse('admin:support_supportcontact_changelist'), {'q': '09123456789'})
    assert response.status_code == 200
    assert '09123456789' in response.content.decode('utf-8')

    response_by_name = client.get(reverse('admin:support_supportcontact_changelist'), {'q': 'Ali'})
    assert response_by_name.status_code == 200
    assert 'Ali Support' in response_by_name.content.decode('utf-8')
