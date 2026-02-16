import logging
import json
import urllib.request
import urllib.error
from typing import Optional, Dict
from django.conf import settings

logger = logging.getLogger('accounts.sms')


class BaseSMSProvider:
    def send_sms(self, to: str, text: str):
        raise NotImplementedError()

    def send_otp(self, to: str, code: str) -> bool:
        """Send OTP code. Returns True on success.

        Default implementation falls back to send_sms with a plain text message.
        Subclasses (e.g. IPPanelProvider) override this to use pattern-based sending.
        """
        self.send_sms(to, f'کد تایید شما: {code}')
        return True


class ConsoleProvider(BaseSMSProvider):
    def send_sms(self, to: str, text: str):
        # log only destination and provider name, never log the OTP code itself
        logger.info(f"[SMS-Console] To={to} (code not logged for security)")

    def send_otp(self, to: str, code: str) -> bool:
        logger.info(f"[SMS-Console] OTP sent to={to} (code not logged for security)")
        return True


class KavenegarStub(BaseSMSProvider):
    def __init__(self, api_key=''):
        self.api_key = api_key

    def send_sms(self, to: str, text: str):
        # stub: in production implement HTTP call to provider
        # log only destination and api_key status, never log the OTP code itself
        logger.info(f"[KavenegarStub] To={to} (code not logged for security, api_key set={bool(self.api_key)})")

    def send_otp(self, to: str, code: str) -> bool:
        logger.info(f"[KavenegarStub] OTP sent to={to} (code not logged)")
        return True


class IPPanelProvider(BaseSMSProvider):
    """IPPanel Edge API provider with pattern-based OTP support.

    Uses the Edge API (https://edge.ippanel.com/v1) for pattern-based SMS sending.
    Patterns are pre-approved message templates with variables — ideal for OTP delivery.

    Required settings:
    - IPPANEL_API_KEY: API key or token from IPPanel
    - IPPANEL_PATTERN_CODE: Pattern code created in IPPanel panel
    - IPPANEL_ORIGINATOR: Sender number (e.g. +983000505)

    Never logs the OTP code itself; logs only destination and status.
    """

    EDGE_BASE_URL = 'https://edge.ippanel.com/v1'
    LEGACY_URL = 'https://rest.ippanel.com/v1/messages'

    def __init__(self, api_key='', sender='', pattern_code='', originator=''):
        self.api_key = api_key
        self.sender = sender
        self.pattern_code = pattern_code or getattr(settings, 'IPPANEL_PATTERN_CODE', '')
        self.originator = originator or getattr(settings, 'IPPANEL_ORIGINATOR', '') or sender

    def _make_request(self, url: str, payload: dict) -> bool:
        """Make an authenticated POST request to IPPanel API."""
        if not self.api_key:
            logger.error('[IPPanel] API key not set; SMS not sent')
            return False

        data = json.dumps(payload).encode('utf-8')
        headers = {
            'Content-Type': 'application/json',
            'Authorization': self.api_key,
        }
        req = urllib.request.Request(url, data=data, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                status = resp.getcode()
                body = resp.read().decode('utf-8', errors='ignore')[:1000]
                if 200 <= status < 300:
                    logger.info(f"[IPPanel] To={payload.get('recipient', '?')} (sent ok)")
                    return True
                else:
                    logger.warning(f"[IPPanel] status={status} body={body}")
                    return False
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode('utf-8', errors='ignore')[:1000]
            except Exception:
                err_body = ''
            logger.error(f"[IPPanel] HTTPError: {e.code} {e.reason} body={err_body}")
            return False
        except Exception as e:
            logger.exception(f"[IPPanel] Error: {e}")
            return False

    def send_sms(self, to: str, text: str):
        """Legacy plain-text SMS sending (fallback)."""
        url = getattr(settings, 'IPPANEL_API_URL', self.LEGACY_URL)
        payload = {'receptor': to, 'message': text}
        if self.sender:
            payload['sender'] = self.sender
        self._make_request(url, payload)

    def send_otp(self, to: str, code: str) -> bool:
        """Send OTP via IPPanel Edge API pattern-based SMS.

        Uses the send endpoint:
        POST {EDGE_BASE_URL}/api/send

        Body:
        {
            "sending_type": "pattern",
            "from_number": "+983000505",
            "code": "pattern_code_here",
            "recipients": ["+989xxxxxxxxx"],
            "params": {"verification-code": "123456"}
        }

        Falls back to legacy plain-text SMS if pattern_code is not configured.
        """
        if not self.pattern_code:
            logger.warning('[IPPanel] No pattern_code set — falling back to plain text SMS')
            self.send_sms(to, f'کد تایید شما: {code}')
            return True

        # Normalize phone to E.164 format (+98...)
        recipient = to.strip()
        if recipient.startswith('0'):
            recipient = '+98' + recipient[1:]

        url = f'{self.EDGE_BASE_URL}/api/send'
        payload = {
            'sending_type': 'pattern',
            'from_number': self.originator,
            'code': self.pattern_code,
            'recipients': [recipient],
            'params': {
                'test': code,
            },
        }
        return self._make_request(url, payload)


def get_sms_provider(provider_name: Optional[str] = None):
    from apps.core.models import SiteSettings

    provider = provider_name or getattr(settings, 'SITE_SMS_PROVIDER', None)
    if not provider:
        try:
            settings_obj = SiteSettings.load()
            provider = settings_obj.sms_provider or 'console'
            sms_enabled = settings_obj.sms_enabled
        except Exception:
            provider = 'console'
            sms_enabled = True
    else:
        sms_enabled = True

    if not sms_enabled:
        return ConsoleProvider()

    if provider == 'kavenegar':
        return KavenegarStub(api_key=getattr(settings, 'KAVENEGAR_API_KEY', ''))
    if provider == 'ippanel':
        return IPPanelProvider(
            api_key=getattr(settings, 'IPPANEL_API_KEY', ''),
            sender=getattr(settings, 'IPPANEL_SENDER', ''),
            pattern_code=getattr(settings, 'IPPANEL_PATTERN_CODE', ''),
            originator=getattr(settings, 'IPPANEL_ORIGINATOR', ''),
        )
    return ConsoleProvider()
