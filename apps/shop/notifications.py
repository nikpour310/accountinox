"""
Order notifications — email invoice + SMS after successful payment.

Called from payment_callback after a verified, successful payment.
"""
import logging
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger('shop.notifications')


def _get_site_settings():
    """Load SiteSettings singleton (returns None on error)."""
    try:
        from apps.core.models import SiteSettings
        return SiteSettings.load()
    except Exception:
        return None


def send_order_email(order):
    """Send an HTML invoice email to the customer after successful payment."""
    if not order.customer_email:
        logger.info('[OrderEmail] No email for order %s — skipped', order.order_number)
        return

    site = _get_site_settings()
    site_name = site.site_name if site else 'Accountinox'
    email_intro = site.order_email_intro if site else ''
    email_footer = site.order_email_footer if site else ''
    support_email = site.email if site else ''
    site_url = getattr(settings, 'SITE_URL', '').strip().rstrip('/')

    items = order.items.select_related('product').all()
    invoice_subtotal = Decimal(getattr(order, 'effective_subtotal', order.total) or 0)
    invoice_vat_amount = Decimal(getattr(order, 'effective_vat_amount', 0) or 0)
    invoice_vat_percent = int(getattr(order, 'effective_vat_percent', 0) or 0)

    context = {
        'order': order,
        'items': items,
        'invoice_subtotal': invoice_subtotal,
        'invoice_vat_amount': invoice_vat_amount,
        'invoice_vat_percent': invoice_vat_percent,
        'invoice_has_vat': invoice_vat_amount > 0,
        'invoice_total': order.total,
        'site_name': site_name,
        'email_intro': email_intro,
        'email_footer': email_footer,
        'support_email': support_email,
        'site_url': site_url,
    }

    subject = f'{site_name} — فاکتور سفارش {order.order_number}'

    try:
        html_body = render_to_string('shop/email/order_invoice.html', context)
        text_body = strip_tags(html_body)

        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', f'noreply@{site_name.lower()}.com')
        msg = EmailMultiAlternatives(subject, text_body, from_email, [order.customer_email])
        msg.attach_alternative(html_body, 'text/html')
        msg.send(fail_silently=True)

        logger.info('[OrderEmail] Sent invoice to %s for order %s', order.customer_email, order.order_number)
    except Exception as exc:
        logger.exception('[OrderEmail] Failed to send email for order %s: %s', order.order_number, exc)


def send_order_sms(order):
    """Send an SMS notification to the customer after successful payment (if enabled in SiteSettings)."""
    site = _get_site_settings()
    if not site:
        logger.warning('[OrderSMS] SiteSettings not loaded — skipped')
        return

    if not site.order_sms_enabled:
        logger.info('[OrderSMS] SMS disabled in settings — skipped for order %s', order.order_number)
        return

    phone = order.customer_phone
    if not phone or phone == 'نامشخص':
        logger.info('[OrderSMS] No phone for order %s — skipped', order.order_number)
        return

    # Build SMS text from template, replacing {order_number}
    sms_template = site.order_sms_text or 'سفارش شما با کد {order_number} با موفقیت ثبت شد.'
    sms_text = sms_template.replace('{order_number}', order.order_number)

    try:
        from apps.accounts.sms_providers import get_sms_provider
        provider = get_sms_provider()
        provider.send_sms(phone, sms_text)
        logger.info('[OrderSMS] Sent SMS to %s for order %s', phone, order.order_number)
    except Exception as exc:
        logger.exception('[OrderSMS] Failed to send SMS for order %s: %s', order.order_number, exc)


def notify_order_success(order):
    """Send both email and SMS notifications for a successful order."""
    send_order_email(order)
    send_order_sms(order)
