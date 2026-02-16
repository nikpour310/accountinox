"""Context processors for the accounts app — injects sidebar data into panel pages."""


def panel_sidebar(request):
    """Provide sidebar stats for the user panel layout.

    Only queries the DB when the user is authenticated so anonymous
    pages remain cheap.  Gracefully returns zeros if tables don't exist yet.
    """
    if not request.user.is_authenticated:
        return {}

    try:
        from apps.shop.models import Order
        from .models import OrderAddress

        user = request.user
        orders_qs = Order.objects.filter(user=user)
        orders_count = orders_qs.count()
        pending_count = orders_qs.filter(paid=False).count()
        addresses_count = OrderAddress.objects.filter(user=user).count()
    except Exception:
        orders_count = 0
        pending_count = 0
        addresses_count = 0

    return {
        'sidebar_orders_count': orders_count,
        'sidebar_pending_count': pending_count,
        'sidebar_addresses_count': addresses_count,
    }
