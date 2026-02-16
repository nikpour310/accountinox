
import json
import logging
import time
from datetime import timedelta

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache
from django.core.mail import send_mail
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST
from django_ratelimit.decorators import ratelimit

from apps.core.models import SiteSettings
from .models import (
    ChatMessage,
    ChatSession,
    SupportAuditLog,
    SupportContact,
    SupportOperatorPresence,
    SupportPushSubscription,
    SupportRating,
)

try:
    from pywebpush import webpush, WebPushException as _webpush_exception_impl
except Exception:  # pragma: no cover
    webpush = None

    class _WebPushExceptionMock(Exception):
        """Fallback exception class when pywebpush is unavailable."""

    _webpush_exception_impl = _WebPushExceptionMock

WebPushException = _webpush_exception_impl  # type: ignore


logger = logging.getLogger('support.chat')
PUSH_LAST_ERROR_CACHE_KEY = 'support.push.last_error'
PUSH_ENDPOINT_PREVIEW_LEN = 30
ONLINE_WINDOW_MINUTES = 5


def _short_endpoint(endpoint):
    endpoint = (endpoint or '').strip()
    if len(endpoint) <= PUSH_ENDPOINT_PREVIEW_LEN:
        return endpoint
    return endpoint[:PUSH_ENDPOINT_PREVIEW_LEN] + '...'


def _set_last_push_error(error_message):
    cache.set(PUSH_LAST_ERROR_CACHE_KEY, error_message, timeout=60 * 60 * 24)


def _get_last_push_error():
    return cache.get(PUSH_LAST_ERROR_CACHE_KEY)


def _clear_last_push_error():
    cache.delete(PUSH_LAST_ERROR_CACHE_KEY)


def _load_json_payload(request):
    content_type = request.headers.get('Content-Type', '')
    if 'application/json' not in content_type.lower():
        return {}
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _wants_json_response(request):
    requested_with = request.headers.get('X-Requested-With', '')
    accepts = request.headers.get('Accept', '')
    return requested_with == 'XMLHttpRequest' or 'application/json' in accepts.lower()


def _is_support_push_enabled(site_settings_obj=None):
    env_enabled = bool(getattr(settings, 'SUPPORT_PUSH_ENABLED', False))
    if site_settings_obj is not None and hasattr(site_settings_obj, 'support_push_enabled'):
        return bool(site_settings_obj.support_push_enabled)
    return env_enabled


def _client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _create_audit_log(action, request=None, session=None, metadata=None, staff_user=None):
    metadata = metadata or {}
    staff = staff_user
    if staff is None and request is not None and request.user.is_authenticated and request.user.is_staff:
        staff = request.user
    try:
        SupportAuditLog.objects.create(
            staff=staff,
            action=action,
            session=session,
            ip=_client_ip(request) if request is not None else '',
            user_agent=request.META.get('HTTP_USER_AGENT', '') if request is not None else '',
            metadata=metadata,
        )
    except Exception:
        logger.exception('Failed to create support audit log for action=%s', action)


def _normalize_phone(phone_raw):
    digits = SupportContact.normalize_phone(phone_raw)
    if len(digits) == 11 and digits.startswith('09'):
        return digits
    return None


def _parse_non_negative_int(raw_value, default=0):
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _resolve_contact_from_request(request):
    contact_id = request.session.get('support_contact_id')
    if contact_id:
        contact = SupportContact.objects.filter(id=contact_id).first()
        if contact:
            return contact
    if request.user.is_authenticated:
        return SupportContact.objects.filter(user=request.user).order_by('-last_seen_at').first()
    return None


def _touch_contact(contact):
    if not contact:
        return
    contact.last_seen_at = timezone.now()
    contact.save(update_fields=['last_seen_at', 'updated_at'])


def _get_active_session_for_contact(contact):
    if not contact:
        return None
    return ChatSession.objects.filter(contact=contact, is_active=True).order_by('-created_at').first()


def _create_session(contact, request, subject='Support Request'):
    if request.user.is_authenticated:
        name_fallback = request.user.get_full_name() or request.user.username
    else:
        name_fallback = 'Guest'
    return ChatSession.objects.create(
        user=request.user if request.user.is_authenticated else (contact.user if contact else None),
        contact=contact,
        user_name=contact.name if contact else name_fallback,
        user_phone=contact.phone if contact else '',
        subject=subject,
        is_active=True,
    )


def _session_from_request_state(request, include_closed=False):
    session_id = request.session.get('support_session_id')
    if session_id:
        session_qs = ChatSession.objects.filter(id=session_id).select_related('contact')
        if not include_closed:
            session_qs = session_qs.filter(is_active=True)
        session = session_qs.first()
        if session:
            return session
    contact = _resolve_contact_from_request(request)
    session = _get_active_session_for_contact(contact)
    if session:
        return session
    if include_closed and contact:
        return ChatSession.objects.filter(contact=contact).select_related('contact').order_by('-created_at').first()
    if request.user.is_authenticated:
        user_qs = ChatSession.objects.filter(user=request.user).select_related('contact').order_by('-created_at')
        if not include_closed:
            user_qs = user_qs.filter(is_active=True)
        return user_qs.first()
    return None


def _store_session_state(request, session):
    if not session:
        return
    request.session['support_session_id'] = session.id
    if session.contact_id:
        request.session['support_contact_id'] = session.contact_id


def _latest_closed_unrated_session(contact):
    if not contact:
        return None
    return (
        ChatSession.objects.filter(contact=contact, is_active=False)
        .select_related('assigned_to', 'operator', 'closed_by')
        .filter(rating__isnull=True)
        .order_by('-closed_at', '-created_at')
        .first()
    )


def _is_rating_owner(request, session):
    if not session:
        return False
    if request.user.is_authenticated and session.user_id and request.user.id == session.user_id:
        return True
    contact_id = request.session.get('support_contact_id')
    return bool(contact_id and session.contact_id and int(contact_id) == session.contact_id)


def _resolve_session_agent(session):
    if not session:
        return None
    return session.assigned_to or session.operator or session.closed_by


def _online_presence_qs():
    cutoff = timezone.now() - timedelta(minutes=ONLINE_WINDOW_MINUTES)
    return SupportOperatorPresence.objects.filter(user__is_staff=True, last_seen_at__gte=cutoff)


def _set_operator_presence(user, active_session_id=None):
    if not user or not user.is_authenticated or not user.is_staff:
        return None
    presence, _ = SupportOperatorPresence.objects.get_or_create(user=user)
    presence.last_seen_at = timezone.now()
    if active_session_id:
        try:
            active_session_id = int(active_session_id)
        except (TypeError, ValueError):
            active_session_id = None
    if active_session_id and ChatSession.objects.filter(id=active_session_id, is_active=True).exists():
        presence.active_session_id = active_session_id
    else:
        presence.active_session = None
    presence.save()
    return presence


def _active_unread_count():
    return ChatMessage.objects.filter(
        read=False,
        is_from_user=True,
        session__is_active=True,
    ).count()

def _send_push_notifications_for_user_message(msg, site_settings_obj=None):
    result = {
        'active_subscriptions': 0,
        'success_count': 0,
        'failure_count': 0,
        'online_staff_count': 0,
        'eligible_staff_count': 0,
    }
    if not _is_support_push_enabled(site_settings_obj=site_settings_obj):
        return result
    if webpush is None:
        logger.warning('Support push is enabled but pywebpush is not installed.')
        _set_last_push_error('pywebpush_not_installed')
        return result

    vapid_private_key = getattr(settings, 'VAPID_PRIVATE_KEY', '')
    if '\\n' in vapid_private_key:
        vapid_private_key = vapid_private_key.replace('\\n', '\n')
    vapid_subject = getattr(settings, 'VAPID_SUBJECT', '')
    if not vapid_private_key or not vapid_subject:
        logger.warning('Support push is enabled but VAPID settings are incomplete.')
        _set_last_push_error('missing_vapid_private_or_subject')
        return result

    online_qs = _online_presence_qs()
    result['online_staff_count'] = online_qs.count()
    eligible_staff_ids = list(
        online_qs.exclude(active_session_id=msg.session_id).values_list('user_id', flat=True)
    )
    result['eligible_staff_count'] = len(eligible_staff_ids)

    subscriptions = SupportPushSubscription.objects.filter(
        user__is_staff=True,
        is_active=True,
        user_id__in=eligible_staff_ids,
    ).select_related('user')
    result['active_subscriptions'] = subscriptions.count()

    logger.info(
        '[Push] dispatch start message_id=%s session_id=%s active_subscriptions=%s online_staff=%s eligible_staff=%s',
        msg.id,
        msg.session_id,
        result['active_subscriptions'],
        result['online_staff_count'],
        result['eligible_staff_count'],
    )
    if result['active_subscriptions'] == 0:
        return result

    trimmed_body = (msg.message or '').strip().replace('\r', ' ').replace('\n', ' ')
    if len(trimmed_body) > 90:
        trimmed_body = trimmed_body[:87] + '...'
    payload = {
        'title': 'پیام جدید پشتیبانی',
        'body': f'{trimmed_body} | گفت‌وگو #{msg.session_id}',
        'url': f'/support/operator/session/{msg.session_id}/',
        'thread_id': msg.session_id,
        'message_id': msg.id,
    }

    _clear_last_push_error()
    for subscription in subscriptions:
        endpoint_preview = _short_endpoint(subscription.endpoint)
        try:
            response = webpush(
                subscription_info={
                    'endpoint': subscription.endpoint,
                    'keys': {
                        'p256dh': subscription.p256dh,
                        'auth': subscription.auth,
                    },
                },
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=vapid_private_key,
                vapid_claims={'sub': vapid_subject},
            )
            status_code = getattr(response, 'status_code', 201)
            result['success_count'] += 1
            logger.info(
                '[Push] webpush success user_id=%s endpoint=%s status=%s',
                subscription.user_id,
                endpoint_preview,
                status_code,
            )
            _create_audit_log(
                action=SupportAuditLog.ACTION_PUSH_SUCCESS,
                session=msg.session,
                staff_user=subscription.user,
                metadata={
                    'message_id': msg.id,
                    'status': status_code,
                    'endpoint': endpoint_preview,
                },
            )
        except WebPushException as exc:
            status_code = getattr(getattr(exc, 'response', None), 'status_code', None)
            disabled = False
            if status_code in (404, 410):
                subscription.is_active = False
                subscription.save(update_fields=['is_active', 'updated_at'])
                disabled = True
            result['failure_count'] += 1
            _set_last_push_error(
                f'webpush_fail status={status_code} user_id={subscription.user_id} endpoint={endpoint_preview}'
            )
            logger.warning(
                '[Push] webpush fail user_id=%s endpoint=%s status=%s disabled=%s',
                subscription.user_id,
                endpoint_preview,
                status_code,
                disabled,
            )
            _create_audit_log(
                action=SupportAuditLog.ACTION_PUSH_FAILURE,
                session=msg.session,
                staff_user=subscription.user,
                metadata={
                    'message_id': msg.id,
                    'status': status_code,
                    'disabled': disabled,
                    'endpoint': endpoint_preview,
                },
            )
        except Exception:
            result['failure_count'] += 1
            _set_last_push_error(
                f'webpush_unexpected user_id={subscription.user_id} endpoint={endpoint_preview}'
            )
            logger.exception(
                '[Push] webpush unexpected_error user_id=%s endpoint=%s',
                subscription.user_id,
                endpoint_preview,
            )
            _create_audit_log(
                action=SupportAuditLog.ACTION_PUSH_FAILURE,
                session=msg.session,
                staff_user=subscription.user,
                metadata={
                    'message_id': msg.id,
                    'status': 'unexpected',
                    'endpoint': endpoint_preview,
                },
            )

    logger.info(
        '[Push] dispatch done message_id=%s session_id=%s success=%s fail=%s',
        msg.id,
        msg.session_id,
        result['success_count'],
        result['failure_count'],
    )
    return result


def support_index(request):
    active_session = _session_from_request_state(request)
    contact = _resolve_contact_from_request(request)
    closed_unrated_session = _latest_closed_unrated_session(contact)
    context = {
        'active_session': active_session,
        'closed_unrated_session': closed_unrated_session,
        'contact': contact,
        'form_name': contact.name if contact else '',
        'form_phone': contact.phone if contact else '',
        'form_errors': {},
    }
    return render(request, 'support/index.html', context)


@require_POST
def start_chat(request):
    name = request.POST.get('name', '').strip()
    phone_raw = request.POST.get('phone', '').strip()
    normalized_phone = _normalize_phone(phone_raw)

    errors = {}
    if not name:
        errors['name'] = 'نام الزامی است.'
    if not normalized_phone:
        errors['phone'] = 'شماره موبایل معتبر وارد کنید (مثال: 09123456789).'

    if errors:
        contact = _resolve_contact_from_request(request)
        return render(
            request,
            'support/index.html',
            {
                'active_session': _session_from_request_state(request),
                'closed_unrated_session': _latest_closed_unrated_session(contact),
                'contact': contact,
                'form_name': name,
                'form_phone': phone_raw,
                'form_errors': errors,
            },
            status=400,
        )

    contact, _ = SupportContact.objects.get_or_create(
        phone=normalized_phone,
        defaults={
            'name': name,
            'user': request.user if request.user.is_authenticated else None,
        },
    )
    should_save = False
    if not contact.name or contact.name != name:
        contact.name = name
        should_save = True
    if request.user.is_authenticated and contact.user_id != request.user.id:
        contact.user = request.user
        should_save = True
    contact.last_seen_at = timezone.now()
    should_save = True
    if should_save:
        contact.save()

    session = _get_active_session_for_contact(contact)
    if not session:
        session = _create_session(contact=contact, request=request)
    else:
        updates = []
        if session.user_name != contact.name:
            session.user_name = contact.name
            updates.append('user_name')
        if session.user_phone != contact.phone:
            session.user_phone = contact.phone
            updates.append('user_phone')
        if session.contact_id != contact.id:
            session.contact = contact
            updates.append('contact')
        if updates:
            session.save(update_fields=updates)

    _store_session_state(request, session)
    return redirect('support:chat_room')


def chat_room(request):
    session = _session_from_request_state(request, include_closed=True)
    if not session:
        return redirect('support:chat')
    _store_session_state(request, session)
    _touch_contact(session.contact)
    messages = session.messages.all()[:200]
    rating = getattr(session, 'rating', None)
    session_agent = _resolve_session_agent(session)
    can_rate = bool(
        (not session.is_active)
        and (rating is None)
        and session_agent
        and _is_rating_owner(request, session)
    )
    return render(request, 'support/chat.html', {
        'session': session,
        'messages': messages,
        'contact': session.contact,
        'session_closed': not session.is_active,
        'can_rate': can_rate,
        'session_rating': rating,
    })


@require_POST
def send_message(request):
    """Send a customer message while keeping long-polling mode."""
    session_id = request.POST.get('session_id')
    message_text = request.POST.get('message', '').strip()

    if not session_id or not message_text:
        return JsonResponse({'error': 'session_id and message required'}, status=400)

    session = ChatSession.objects.filter(id=session_id).select_related('contact').first()
    if not session:
        return JsonResponse({'error': 'session not found'}, status=404)

    # Security: block access if caller doesn't own this session
    if request.user.is_authenticated:
        if not request.user.is_staff and session.user_id and session.user_id != request.user.id:
            return JsonResponse({'error': 'forbidden'}, status=403)
    # anonymous users allowed to post messages by session id (no session cookie required)

    if not session.is_active:
        contact = session.contact or _resolve_contact_from_request(request)
        session = ChatSession.objects.create(
            user=request.user if request.user.is_authenticated else session.user,
            contact=contact,
            user_name=(contact.name if contact else (session.user_name or 'Guest')),
            user_phone=(contact.phone if contact else session.user_phone),
            user_email=session.user_email,
            subject=session.subject or 'Support Request',
            is_active=True,
        )

    if session.contact:
        _touch_contact(session.contact)
        updates = []
        if session.user_name != session.contact.name:
            session.user_name = session.contact.name
            updates.append('user_name')
        if session.user_phone != session.contact.phone:
            session.user_phone = session.contact.phone
            updates.append('user_phone')
        if updates:
            session.save(update_fields=updates)

    _store_session_state(request, session)
    sender_name = session.user_name
    if not sender_name:
        if request.user.is_authenticated:
            sender_name = request.user.get_full_name() or request.user.username
        else:
            sender_name = 'Guest'
    msg = ChatMessage.objects.create(
        session=session,
        user=request.user if request.user.is_authenticated else None,
        name=sender_name,
        message=message_text,
        is_from_user=True,
        read=False,
    )

    logger.info('[Chat] Message %s sent in session %s', msg.id, session.id)
    settings_obj = None
    try:
        settings_obj = SiteSettings.load()
        if settings_obj.support_email_notifications_enabled and settings_obj.support_notify_email:
            try:
                send_mail(
                    subject=f'New support message (session {session.id})',
                    message=f'New message from {msg.name or "Guest"}:\\n\\n{msg.message}',
                    from_email=None,
                    recipient_list=[settings_obj.support_notify_email],
                    fail_silently=True,
                )
            except Exception:
                logger.exception('Failed to send support notification email')
    except Exception:
        logger.debug('SiteSettings not available for support notifications')
        settings_obj = None

    try:
        push_result = _send_push_notifications_for_user_message(msg, site_settings_obj=settings_obj)
        logger.info(
            '[Push] send_message summary message_id=%s active_subscriptions=%s success=%s fail=%s',
            msg.id,
            push_result.get('active_subscriptions', 0),
            push_result.get('success_count', 0),
            push_result.get('failure_count', 0),
        )
    except Exception:
        logger.exception('Failed while dispatching support push notifications')

    return JsonResponse({
        'ok': True,
        'message_id': msg.id,
        'created_at': msg.created_at.isoformat(),
        'session_id': session.id,
    })


def get_messages(request):
    """Long-polling endpoint for retrieving new messages."""
    session_id = request.GET.get('session_id')
    last_id = _parse_non_negative_int(request.GET.get('last_id'), default=0)
    timeout = _parse_non_negative_int(request.GET.get('timeout'), default=30)
    timeout = max(1, min(timeout, 30))

    if not session_id:
        return JsonResponse({'error': 'session_id required'}, status=400)

    try:
        session = ChatSession.objects.get(id=session_id)
    except ChatSession.DoesNotExist:
        return JsonResponse({'error': 'session not found'}, status=404)

    # Security: verify caller owns this session or is staff
    if request.user.is_authenticated:
        if not request.user.is_staff and session.user_id and session.user_id != request.user.id:
            return JsonResponse({'error': 'forbidden'}, status=403)
    # anonymous users allowed to long-poll by session id

    start_time = time.time()
    while (time.time() - start_time) < timeout:
        messages = session.messages.filter(id__gt=last_id).values(
            'id', 'name', 'message', 'is_from_user', 'created_at'
        )
        if messages.exists():
            messages_list = []
            for m in messages:
                messages_list.append({
                    'id': m['id'],
                    'name': m['name'],
                    'message': m['message'],
                    'is_from_user': m['is_from_user'],
                    'created_at': m['created_at'].isoformat(),
                })
            new_last_id = messages.last()['id'] if messages else last_id
            return JsonResponse({'messages': messages_list, 'last_id': new_last_id})
        time.sleep(2)

    return JsonResponse({'messages': [], 'last_id': last_id})


def poll_messages(request):
    """Long-polling endpoint compatible with both user and operator views."""
    thread_id = request.GET.get('thread_id') or request.GET.get('session_id')
    since = _parse_non_negative_int(request.GET.get('since'), default=0)
    timeout = _parse_non_negative_int(request.GET.get('timeout'), default=10)
    timeout = max(1, min(timeout, 30))

    session = None
    if thread_id:
        try:
            session = ChatSession.objects.get(id=thread_id)
        except ChatSession.DoesNotExist:
            return JsonResponse({'error': 'thread not found'}, status=404)
    else:
        session = _session_from_request_state(request)
        if not session:
            return JsonResponse({'error': 'thread_id required or no active session found'}, status=400)

    # Security: verify caller owns this session or is staff
    if request.user.is_authenticated:
        if not request.user.is_staff and session.user_id and session.user_id != request.user.id:
            return JsonResponse({'error': 'forbidden'}, status=403)
    # anonymous allowed for poll_messages by session id

    start_time = time.time()
    while (time.time() - start_time) < timeout:
        qs = session.messages.filter(id__gt=since)
        if qs.exists():
            messages_list = []
            for m in qs:
                messages_list.append({
                    'id': m.id,
                    'name': m.name,
                    'message': m.message,
                    'is_from_user': m.is_from_user,
                    'created_at': m.created_at.isoformat(),
                })
            return JsonResponse({'messages': messages_list, 'since': messages_list[-1]['id']})
        time.sleep(1)

    return JsonResponse({'messages': [], 'since': since})


@require_http_methods(['GET', 'POST'])
def rate_session(request, session_id):
    session = get_object_or_404(
        ChatSession.objects.select_related('assigned_to', 'operator', 'closed_by', 'contact'),
        id=session_id,
    )
    wants_json = _wants_json_response(request)

    if not _is_rating_owner(request, session):
        if wants_json:
            return JsonResponse({'error': 'forbidden'}, status=403)
        return redirect('support:chat')
    _store_session_state(request, session)
    if session.is_active:
        if wants_json:
            return JsonResponse({'error': 'session must be closed before rating'}, status=400)
        return render(
            request,
            'support/rate_session.html',
            {
                'session': session,
                'rating_errors': {'score': 'ثبت امتیاز فقط برای گفتگوی بسته ممکن است.'},
                'existing_rating': getattr(session, 'rating', None),
                'form_score': '',
                'form_reason': '',
                'agent': _resolve_session_agent(session),
            },
            status=400,
        )

    agent = _resolve_session_agent(session)
    if not agent:
        if wants_json:
            return JsonResponse({'error': 'session has no assigned agent'}, status=400)
        return render(
            request,
            'support/rate_session.html',
            {
                'session': session,
                'rating_errors': {'score': 'برای این گفتگو اپراتور مشخص نشده است.'},
                'existing_rating': getattr(session, 'rating', None),
                'form_score': '',
                'form_reason': '',
                'agent': None,
            },
            status=400,
        )

    existing_rating = getattr(session, 'rating', None)
    if request.method == 'GET':
        return render(
            request,
            'support/rate_session.html',
            {
                'session': session,
                'agent': agent,
                'existing_rating': existing_rating,
                'rating_errors': {},
                'form_score': existing_rating.score if existing_rating else '',
                'form_reason': existing_rating.reason if existing_rating else '',
            },
        )

    if existing_rating is not None:
        if wants_json:
            return JsonResponse({'error': 'rating already submitted'}, status=409)
        return render(
            request,
            'support/rate_session.html',
            {
                'session': session,
                'agent': agent,
                'existing_rating': existing_rating,
                'rating_errors': {'score': 'برای این گفتگو قبلاً امتیاز ثبت شده است.'},
                'form_score': existing_rating.score,
                'form_reason': existing_rating.reason,
            },
            status=409,
        )

    score_raw = (request.POST.get('score') or '').strip()
    reason = (request.POST.get('reason') or '').strip()
    errors = {}
    try:
        score = int(score_raw)
    except (TypeError, ValueError):
        score = None
    if score is None or score < 1 or score > 5:
        errors['score'] = 'امتیاز باید عددی بین 1 تا 5 باشد.'
    if score == 1 and not reason:
        errors['reason'] = 'برای امتیاز 1 ثبت دلیل الزامی است.'

    if errors:
        status_code = 400
        if wants_json:
            return JsonResponse({'errors': errors}, status=status_code)
        return render(
            request,
            'support/rate_session.html',
            {
                'session': session,
                'agent': agent,
                'existing_rating': None,
                'rating_errors': errors,
                'form_score': score_raw,
                'form_reason': reason,
            },
            status=status_code,
        )

    rating = SupportRating(session=session, agent=agent, score=score, reason=reason)
    try:
        rating.save()
    except Exception:
        logger.exception('Failed to store support rating for session=%s', session.id)
        if wants_json:
            return JsonResponse({'error': 'could not save rating'}, status=400)
        return render(
            request,
            'support/rate_session.html',
            {
                'session': session,
                'agent': agent,
                'existing_rating': None,
                'rating_errors': {'score': 'ثبت امتیاز با خطا مواجه شد.'},
                'form_score': score_raw,
                'form_reason': reason,
            },
            status=400,
        )

    if wants_json:
        return JsonResponse({'ok': True, 'score': rating.score})
    return redirect(f'{reverse("support:chat_room")}?rated=1')


@staff_member_required
def operator_dashboard(request):
    _set_operator_presence(request.user, active_session_id=None)
    active_sessions = ChatSession.objects.filter(is_active=True).select_related('contact', 'user').annotate(
        unread_count=Count('messages', filter=Q(messages__read=False, messages__is_from_user=True))
    ).order_by('-created_at')
    return render(request, 'support/operator_dashboard.html', {
        'active_sessions': active_sessions,
        'unread_count': _active_unread_count(),
        'support_push_enabled': bool(
            getattr(settings, 'SUPPORT_PUSH_ENABLED', False) and getattr(settings, 'VAPID_PUBLIC_KEY', '')
        ),
        'support_push_public_key': getattr(settings, 'VAPID_PUBLIC_KEY', ''),
        'rate_limited': request.GET.get('rate_limited') == '1',
    })


@staff_member_required
def operator_session_view(request, session_id):
    session = get_object_or_404(ChatSession.objects.select_related('contact', 'user'), id=session_id)
    if not session.is_active:
        return redirect('support:operator_dashboard')

    _set_operator_presence(request.user, active_session_id=session.id)
    session_updates = []
    if session.assigned_to_id is None:
        session.assigned_to = request.user
        session_updates.append('assigned_to')
    if session.operator_id is None:
        session.operator = request.user
        session_updates.append('operator')
    if session_updates:
        session.save(update_fields=session_updates)

    ChatMessage.objects.filter(session=session, is_from_user=True, read=False).update(read=True)
    _create_audit_log(
        action=SupportAuditLog.ACTION_OPEN,
        request=request,
        session=session,
        metadata={'session_id': session.id},
    )

    active_sessions = ChatSession.objects.filter(is_active=True).select_related('contact', 'user').annotate(
        unread_count=Count('messages', filter=Q(messages__read=False, messages__is_from_user=True))
    ).order_by('-created_at')
    messages = session.messages.all()[:300]
    last_message_id = session.messages.order_by('-id').values_list('id', flat=True).first() or 0
    return render(request, 'support/operator_session.html', {
        'session': session,
        'messages': messages,
        'last_message_id': last_message_id,
        'active_sessions': active_sessions,
        'unread_count': _active_unread_count(),
        'support_push_enabled': bool(
            getattr(settings, 'SUPPORT_PUSH_ENABLED', False) and getattr(settings, 'VAPID_PUBLIC_KEY', '')
        ),
        'support_push_public_key': getattr(settings, 'VAPID_PUBLIC_KEY', ''),
        'rate_limited': request.GET.get('rate_limited') == '1',
    })


@staff_member_required
@require_POST
@ratelimit(key='user_or_ip', rate='20/m', method='POST', block=False)
def operator_send_message(request):
    """Operator sending a response message."""
    wants_json = _wants_json_response(request)
    session_id = request.POST.get('session_id')
    message_text = request.POST.get('message', '').strip()

    if getattr(request, 'limited', False):
        _create_audit_log(
            action=SupportAuditLog.ACTION_SEND,
            request=request,
            metadata={'rate_limited': True, 'session_id': session_id},
        )
        if wants_json:
            return JsonResponse({'error': 'rate limit exceeded'}, status=429)
        if session_id:
            return redirect(f'{reverse("support:operator_session", args=[session_id])}?rate_limited=1')
        return redirect(f'{reverse("support:operator_dashboard")}?rate_limited=1')

    if not session_id or not message_text:
        if wants_json:
            return JsonResponse({'error': 'session_id and message required'}, status=400)
        if session_id:
            return redirect(reverse('support:operator_session', args=[session_id]))
        return redirect('support:operator_dashboard')

    session = ChatSession.objects.filter(id=session_id).first()
    if not session:
        if wants_json:
            return JsonResponse({'error': 'session not found'}, status=404)
        return redirect('support:operator_dashboard')
    if not session.is_active:
        if wants_json:
            return JsonResponse({'error': 'session is closed'}, status=400)
        return redirect('support:operator_dashboard')

    session_updates = []
    if session.assigned_to_id != request.user.id:
        session.assigned_to = request.user
        session_updates.append('assigned_to')
    if session.operator_id != request.user.id:
        session.operator = request.user
        session_updates.append('operator')
    if session_updates:
        session.save(update_fields=session_updates)

    msg = ChatMessage.objects.create(
        session=session,
        user=request.user,
        name=request.user.get_full_name() or request.user.username,
        message=message_text,
        is_from_user=False,
        read=True,
    )
    logger.info('[Chat] Operator %s sent message %s in session %s', request.user, msg.id, session.id)
    _create_audit_log(
        action=SupportAuditLog.ACTION_SEND,
        request=request,
        session=session,
        metadata={'message_id': msg.id},
    )

    if wants_json:
        return JsonResponse({
            'ok': True,
            'message_id': msg.id,
            'created_at': msg.created_at.isoformat(),
            'name': msg.name,
            'message': msg.message,
            'is_from_user': msg.is_from_user,
        })
    return redirect(reverse('support:operator_session', args=[session.id]))


@staff_member_required
@require_http_methods(["GET", "POST"])
def close_session(request, session_id):
    """Close a support session."""
    session = get_object_or_404(ChatSession, id=session_id)
    marked_count = ChatMessage.objects.filter(
        session=session,
        is_from_user=True,
        read=False,
    ).update(read=True)
    close_updates = ['is_active', 'closed_at', 'closed_by']
    session.is_active = False
    session.closed_at = timezone.now()
    session.closed_by = request.user
    if session.assigned_to_id is None:
        session.assigned_to = request.user
        close_updates.append('assigned_to')
    if session.operator_id is None:
        session.operator = request.user
        close_updates.append('operator')
    session.save(update_fields=close_updates)
    _set_operator_presence(request.user, active_session_id=None)
    _create_audit_log(
        action=SupportAuditLog.ACTION_CLOSE,
        request=request,
        session=session,
        metadata={'marked_read': marked_count},
    )
    logger.info(
        '[Chat] Session %s closed by %s (marked_read=%s)',
        session.id,
        request.user,
        marked_count,
    )
    return redirect('support:operator_dashboard')


@staff_member_required
@require_POST
def push_subscribe(request):
    payload = _load_json_payload(request)
    if payload is None:
        return JsonResponse({'error': 'invalid JSON payload'}, status=400)

    endpoint = (payload.get('endpoint') or request.POST.get('endpoint') or '').strip()
    keys = payload.get('keys') or {}
    p256dh = (keys.get('p256dh') or payload.get('p256dh') or request.POST.get('p256dh') or '').strip()
    auth_key = (keys.get('auth') or payload.get('auth') or request.POST.get('auth') or '').strip()
    active_session_id = payload.get('active_session_id') or request.POST.get('active_session_id')

    if not endpoint or not p256dh or not auth_key:
        return JsonResponse({'error': 'endpoint and keys are required'}, status=400)

    subscription, created = SupportPushSubscription.objects.update_or_create(
        user=request.user,
        endpoint=endpoint,
        defaults={
            'p256dh': p256dh,
            'auth': auth_key,
            'is_active': True,
        },
    )
    _set_operator_presence(request.user, active_session_id=active_session_id)

    active_subs_total = SupportPushSubscription.objects.filter(user__is_staff=True, is_active=True).count()
    active_subs_user = SupportPushSubscription.objects.filter(user=request.user, is_active=True).count()
    logger.info(
        '[Push] subscribe staff_id=%s endpoint=%s active_subscriptions=%s user_active_subscriptions=%s created=%s',
        request.user.id,
        _short_endpoint(endpoint),
        active_subs_total,
        active_subs_user,
        created,
    )
    _create_audit_log(
        action=SupportAuditLog.ACTION_SUBSCRIBE,
        request=request,
        metadata={
            'endpoint': _short_endpoint(endpoint),
            'active_subs': active_subs_total,
            'user_active_subs': active_subs_user,
            'created': created,
        },
    )
    return JsonResponse({
        'ok': True,
        'created': created,
        'subscription_id': subscription.id,
        'active_subs': active_subs_total,
        'active_subs_user': active_subs_user,
    })


@staff_member_required
@require_POST
def push_unsubscribe(request):
    payload = _load_json_payload(request)
    if payload is None:
        return JsonResponse({'error': 'invalid JSON payload'}, status=400)

    endpoint = (payload.get('endpoint') or request.POST.get('endpoint') or '').strip()
    subscriptions = SupportPushSubscription.objects.filter(user=request.user, is_active=True)
    if endpoint:
        subscriptions = subscriptions.filter(endpoint=endpoint)
    updated_count = subscriptions.update(is_active=False, updated_at=timezone.now())

    logger.info(
        '[Push] unsubscribe staff_id=%s endpoint=%s updated=%s active_subscriptions=%s',
        request.user.id,
        _short_endpoint(endpoint) if endpoint else '*',
        updated_count,
        SupportPushSubscription.objects.filter(user__is_staff=True, is_active=True).count(),
    )
    _create_audit_log(
        action=SupportAuditLog.ACTION_UNSUBSCRIBE,
        request=request,
        metadata={
            'endpoint': _short_endpoint(endpoint) if endpoint else '*',
            'updated': updated_count,
        },
    )
    return JsonResponse({'ok': True, 'updated': updated_count})


@staff_member_required
@require_http_methods(['GET'])
def operator_unread_status(request):
    _set_operator_presence(request.user, active_session_id=request.GET.get('session_id'))
    return JsonResponse({
        'ok': True,
        'unread_count': _active_unread_count(),
    })


@staff_member_required
@require_http_methods(['GET'])
def operator_presence(request):
    presence = _set_operator_presence(request.user, active_session_id=request.GET.get('session_id'))
    return JsonResponse({
        'ok': True,
        'last_seen_at': presence.last_seen_at.isoformat() if presence else None,
        'active_session_id': presence.active_session_id if presence else None,
    })


@staff_member_required
@require_http_methods(['GET'])
def push_debug(request):
    return JsonResponse({
        'enabled': _is_support_push_enabled(),
        'vapid_public_present': bool(getattr(settings, 'VAPID_PUBLIC_KEY', '')),
        'subs_count': SupportPushSubscription.objects.filter(user__is_staff=True).count(),
        'active_subs': SupportPushSubscription.objects.filter(user__is_staff=True, is_active=True).count(),
        'online_staff_count': _online_presence_qs().count(),
        'last_error': _get_last_push_error(),
    })
