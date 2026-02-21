"""
Payment Gateway Adapters: ZarinPal and Zibal
Handles payment initiation and verification
"""
import logging
from typing import Any, Dict, Tuple

import requests  # type: ignore
from django.conf import settings

logger = logging.getLogger('shop.payment')


class PaymentProvider:
    """Base class for payment gateway providers"""
    
    def __init__(self, merchant_id: str = '', callback_url: str = ''):
        self.merchant_id = merchant_id
        self.callback_url = callback_url
    
    def initiate_payment(self, amount: int, order_id: int, description: str = '') -> Tuple[bool, Dict[str, Any]]:
        """
        Initiate a payment request.
        Returns: (success: bool, {reference: str, payment_url: str} or {error: str})
        """
        raise NotImplementedError()
    
    def verify_payment(
        self,
        reference: str,
        authority: str = '',
        expected_amount: int | None = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Verify payment after callback.
        Returns: (success: bool, {amount: int, status: str} or {error: str})
        """
        raise NotImplementedError()


class ZarinPalProvider(PaymentProvider):
    """ZarinPal payment gateway adapter"""
    
    def __init__(self, merchant_id: str = '', callback_url: str = '', sandbox: bool = True):
        super().__init__(merchant_id, callback_url)
        self.sandbox = sandbox
        self.base_url = 'https://sandbox.zarinpal.com/pg' if sandbox else 'https://www.zarinpal.com/pg'
    
    def initiate_payment(self, amount: int, order_id: int, description: str = '') -> Tuple[bool, Dict[str, Any]]:
        """ZarinPal request payment"""
        if not self.merchant_id:
            return False, {'error': 'merchant_id not configured'}
        
        url = f'{self.base_url}/rest/WebGate/PaymentRequest.json'
        payload = {
            'MerchantID': self.merchant_id,
            'Amount': int(amount),  # Rials
            'Description': description or f'Order #{order_id}',
            'CallbackURL': self.callback_url,
        }
        
        try:
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()
            
            if data.get('Status') == 100:
                authority = data.get('Authority', '')
                payment_url = f'{self.base_url}/StartPay/{authority}'
                logger.info(f'[ZarinPal] Initiated payment: order={order_id}, authority={authority}')
                return True, {'reference': authority, 'payment_url': payment_url}
            else:
                error = f"ZarinPal error: {data.get('Status', 'unknown')}"
                logger.warning(f'[ZarinPal] Initiative failed: {error}')
                return False, {'error': error}
        except requests.RequestException as exc:
            logger.exception('[ZarinPal] Network error during initiation: %s', exc)
            return False, {'error': f'Network error: {exc}'}
        except ValueError as exc:
            logger.exception('[ZarinPal] Invalid JSON during initiation: %s', exc)
            return False, {'error': f'Invalid gateway response: {exc}'}
    
    def verify_payment(
        self,
        reference: str,
        authority: str = '',
        expected_amount: int | None = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """ZarinPal verify payment"""
        if not self.merchant_id:
            return False, {'error': 'merchant_id not configured'}
        
        auth = authority or reference  # ZarinPal uses Authority/reference interchangeably
        url = f'{self.base_url}/rest/WebGate/PaymentVerification.json'
        verify_amount = int(expected_amount) if expected_amount is not None else 0
        payload = {
            'MerchantID': self.merchant_id,
            'Authority': auth,
            'Amount': verify_amount,
        }
        
        try:
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()
            
            if data.get('Status') == 100:
                ref_id = data.get('RefID', '')
                amount = data.get('Amount', 0)
                logger.info(f'[ZarinPal] Payment verified: ref_id={ref_id}, amount=%s expected=%s', amount, verify_amount)
                return True, {'amount': amount, 'reference': ref_id, 'status': 'verified'}
            else:
                error = f"ZarinPal verification failed: Status {data.get('Status', 'unknown')}"
                logger.warning(f'[ZarinPal] Verification failed: {error}')
                return False, {'error': error, 'status': data.get('Status')}
        except requests.RequestException as exc:
            logger.exception('[ZarinPal] Network error during verification: %s', exc)
            return False, {'error': f'Network error: {exc}'}
        except ValueError as exc:
            logger.exception('[ZarinPal] Invalid JSON during verification: %s', exc)
            return False, {'error': f'Invalid gateway response: {exc}'}


class ZibalProvider(PaymentProvider):
    """Zibal payment gateway adapter"""
    
    def __init__(self, merchant_id: str = '', callback_url: str = '', sandbox: bool = True):
        super().__init__(merchant_id, callback_url)
        self.sandbox = sandbox
        self.base_url = 'https://sandbox.zibal.ir/api' if sandbox else 'https://api.zibal.ir/api'
    
    def initiate_payment(self, amount: int, order_id: int, description: str = '') -> Tuple[bool, Dict[str, Any]]:
        """Zibal request payment"""
        if not self.merchant_id:
            return False, {'error': 'merchant_id not configured'}
        
        url = f'{self.base_url}/v1/request'
        payload = {
            'merchant': self.merchant_id,
            'amount': int(amount),  # Rials
            'callbackUrl': self.callback_url,
            'description': description or f'Order #{order_id}',
            'orderId': str(order_id),
        }
        
        try:
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()
            
            if data.get('result') == 0:
                track_id = data.get('trackId', '')
                payment_url = f'https://gateway.zibal.ir/start/{track_id}'
                logger.info(f'[Zibal] Initiated payment: order={order_id}, track_id={track_id}')
                return True, {'reference': track_id, 'payment_url': payment_url}
            else:
                error = f"Zibal error: {data.get('message', 'unknown')}"
                logger.warning(f'[Zibal] Initiative failed: {error}')
                return False, {'error': error}
        except requests.RequestException as exc:
            logger.exception('[Zibal] Network error during initiation: %s', exc)
            return False, {'error': f'Network error: {exc}'}
        except ValueError as exc:
            logger.exception('[Zibal] Invalid JSON during initiation: %s', exc)
            return False, {'error': f'Invalid gateway response: {exc}'}
    
    def verify_payment(
        self,
        reference: str,
        authority: str = '',
        expected_amount: int | None = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """Zibal verify payment"""
        if not self.merchant_id:
            return False, {'error': 'merchant_id not configured'}
        
        url = f'{self.base_url}/v1/verify'
        payload = {
            'merchant': self.merchant_id,
            'trackId': reference,
        }
        
        try:
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()
            
            if data.get('result') == 0:
                amount = data.get('amount', 0)
                logger.info(f'[Zibal] Payment verified: reference={reference}, amount={amount}')
                return True, {'amount': amount, 'reference': reference, 'status': 'verified'}
            else:
                error = f"Zibal verification failed: {data.get('message', 'unknown')}"
                logger.warning(f'[Zibal] Verification failed: {error}')
                return False, {'error': error, 'status': data.get('result')}
        except requests.RequestException as exc:
            logger.exception('[Zibal] Network error during verification: %s', exc)
            return False, {'error': f'Network error: {exc}'}
        except ValueError as exc:
            logger.exception('[Zibal] Invalid JSON during verification: %s', exc)
            return False, {'error': f'Invalid gateway response: {exc}'}


def get_payment_provider(gateway_name: str = '', merchant_id: str = '', callback_url: str = '') -> PaymentProvider:
    """Factory function to get payment provider instance"""
    from apps.core.models import SiteSettings
    
    provider_name = gateway_name
    if not provider_name:
        try:
            settings_obj = SiteSettings.load()
            provider_name = settings_obj.payment_gateway or 'zarinpal'
        except Exception as exc:
            logger.warning('[Payment Provider] Falling back to default provider due to settings error: %s', exc)
            provider_name = 'zarinpal'
    
    sandbox = bool(getattr(settings, 'PAYMENT_SANDBOX', True))
    if provider_name == 'zibal':
        return ZibalProvider(merchant_id, callback_url, sandbox=sandbox)
    return ZarinPalProvider(merchant_id, callback_url, sandbox=sandbox)
