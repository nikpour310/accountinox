from typing import Tuple, Optional
from django.conf import settings


class BaseGateway:
    name = 'base'

    def start_payment(self, order):
        raise NotImplementedError()

    def verify(self, request) -> Tuple[bool, dict]:
        raise NotImplementedError()


class ZarinpalGateway(BaseGateway):
    name = 'zarinpal'

    def start_payment(self, order):
        # In production: redirect to provider with order info
        return '/shop/payment/callback/zarinpal/?mock=1&order_id=%s' % order.id

    def verify(self, request):
        # Mock verification for testing
        order_id = request.GET.get('order_id') or request.POST.get('order_id')
        return True, {'order_id': int(order_id) if order_id else None}


class ZibalGateway(BaseGateway):
    name = 'zibal'

    def start_payment(self, order):
        return '/shop/payment/callback/zibal/?mock=1&order_id=%s' % order.id

    def verify(self, request):
        order_id = request.GET.get('order_id') or request.POST.get('order_id')
        return True, {'order_id': int(order_id) if order_id else None}


def get_gateway(provider_name: Optional[str] = None):
    name = provider_name or getattr(settings, 'SITE_PAYMENT_GATEWAY', 'zarinpal')
    if name == 'zibal':
        return ZibalGateway()
    return ZarinpalGateway()
