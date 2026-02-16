from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver


@receiver(user_logged_in)
def load_cart_on_login(sender, request, user, **kwargs):
    """When a user logs in, merge their DB cart into the session cart."""
    from .views import _load_cart_from_db
    try:
        _load_cart_from_db(request)
    except Exception:
        pass
