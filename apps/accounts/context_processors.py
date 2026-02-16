"""Context processors for the accounts app — injects sidebar data into panel pages."""
from apps.shop.models import Order


def panel_sidebar(request):
    """Provide sidebar stats for the user panel layout.

    Only queries the DB when the user is authenticated so anonymous
    pages remain cheap.
    """
    if not request.user.is_authenticated:
        return {}

    user = request.user

    orders_qs = Order.objects.filter(user=user)
    orders_count = orders_qs.count()
    pending_count = orders_qs.filter(paid=False).count()

    from .models import OrderAddress
    addresses_count = OrderAddress.objects.filter(user=user).count()

    return {
        'sidebar_orders_count': orders_count,
        'sidebar_pending_count': pending_count,
        'sidebar_addresses_count': addresses_count,
    }
