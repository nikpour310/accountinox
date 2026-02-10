import pytest
from django.contrib.auth.models import User

from apps.shop.models import Order


@pytest.mark.django_db
def test_order_default_status_is_pending_review():
    user = User.objects.create_user(username='status_user', password='pass123456')
    order = Order.objects.create(user=user, total='50.00')
    assert order.status == Order.STATUS_PENDING_REVIEW
    assert order.get_status_display() == 'درحال بررسی'


@pytest.mark.django_db
def test_order_timeline_steps_follow_status():
    order = Order.objects.create(total='10.00', status=Order.STATUS_CONFIRMED)
    steps = order.timeline_steps()
    assert len(steps) == 3
    assert steps[0]['state'] == 'done'
    assert steps[1]['state'] == 'current'
    assert steps[2]['state'] == 'pending'

