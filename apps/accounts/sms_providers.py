import logging
from typing import Optional
from django.conf import settings

logger = logging.getLogger('accounts.sms')


class BaseSMSProvider:
    def send_sms(self, to: str, text: str):
        raise NotImplementedError()


class ConsoleProvider(BaseSMSProvider):
    def send_sms(self, to: str, text: str):
        # log only destination and provider name, never log the OTP code itself
        logger.info(f"[SMS-Console] To={to} (code not logged for security)")


class KavenegarStub(BaseSMSProvider):
    def __init__(self, api_key=''):
        self.api_key = api_key

    def send_sms(self, to: str, text: str):
        # stub: in production implement HTTP call to provider
        # log only destination and api_key status, never log the OTP code itself
        logger.info(f"[KavenegarStub] To={to} (code not logged for security, api_key set={bool(self.api_key)})")


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
    return ConsoleProvider()
