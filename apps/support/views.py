
import json
import logging
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from datetime import timedelta

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache
from django.core.mail import send_mail
from django.db.models import Count, Max, OuterRef, Q, Subquery
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
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
TYPING_TIMEOUT_SECONDS = 8
POLL_MAX_TIMEOUT_SECONDS = 8
POLL_SLEEP_SECONDS = 0.5
POLL_OPEN_CONNECTIONS_CACHE_KEY = 'support.poll.open_connections'
POLL_LAST_LATENCY_CACHE_KEY = 'support.poll.last_latency_ms'
POLL_ACTIVE_LOCK_PREFIX = 'support.poll.active'
POLL_SIGNATURE_PREFIX = 'support.poll.signature'


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
    session_token = (request.session.get('support_session_token') or '').strip()
    if session_token:
        session_qs = ChatSession.objects.filter(public_token=session_token).select_related('contact')
        if not include_closed:
            session_qs = session_qs.filter(is_active=True)
        session = session_qs.first()
        if session:
            return session

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
    request.session['support_session_token'] = session.public_token
    if session.contact_id:
        request.session['support_contact_id'] = session.contact_id


def _session_from_inputs(*, session_id=None, session_token=None, include_closed=True):
    token = (session_token or '').strip()
    if token:
        qs = ChatSession.objects.filter(public_token=token).select_related('contact')
        if not include_closed:
            qs = qs.filter(is_active=True)
        return qs.first()

    parsed_id = _parse_non_negative_int(session_id, default=0)
    if not parsed_id:
        return None
    qs = ChatSession.objects.filter(id=parsed_id).select_related('contact')
    if not include_closed:
        qs = qs.filter(is_active=True)
    return qs.first()


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


def _is_session_owner(request, session):
    return _is_rating_owner(request, session)


def _safe_next_url(request, fallback='support:chat_room'):
    next_url = (request.POST.get('next') or request.GET.get('next') or '').strip()
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return reverse(fallback)


def _add_or_replace_query_param(url, key, value):
    parsed = urlsplit(url)
    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_params[key] = value
    new_query = urlencode(query_params, doseq=True)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment))


def _ticket_action_feedback(action):
    normalized = (action or '').strip().lower()
    if normalized == 'closed':
        return 'گفتگو با موفقیت بسته شد.', 'alert alert-info'
    if normalized == 'reopened':
        return 'گفتگو با موفقیت بازگشایی شد.', 'alert alert-success'
    return '', ''


def _decorate_session_status(session):
    if not session:
        return
    if not hasattr(session, 'last_message_from_user'):
        session.last_message_from_user = (
            session.messages.order_by('-created_at', '-id').values_list('is_from_user', flat=True).first()
        )
    if not hasattr(session, 'last_message_at'):
        session.last_message_at = (
            session.messages.order_by('-created_at', '-id').values_list('created_at', flat=True).first()
        )
    status_key, status_label, status_badge_class = _session_status_meta(session)
    session.status_key = status_key
    session.status_label = status_label
    session.status_badge_class = status_badge_class


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


def _operator_queue_realtime_snapshot():
    """
    Lightweight queue snapshot for operator dashboard live-sync.
    Used by polling to detect queue changes and refresh UI automatically.
    """
    unread_count = _active_unread_count()
    active_qs = ChatSession.objects.filter(is_active=True)
    total_active = active_qs.count()
    latest_session_id = active_qs.aggregate(max_id=Max('id')).get('max_id') or 0
    latest_message_id = ChatMessage.objects.filter(session__is_active=True).aggregate(max_id=Max('id')).get('max_id') or 0
    signature = f'{total_active}:{unread_count}:{latest_session_id}:{latest_message_id}'
    return {
        'unread_count': unread_count,
        'total_active': total_active,
        'latest_session_id': latest_session_id,
        'latest_message_id': latest_message_id,
        'signature': signature,
    }


def _parse_bool(raw_value):
    if isinstance(raw_value, bool):
        return raw_value
    if raw_value is None:
        return False
    normalized = str(raw_value).strip().lower()
    return normalized in {'1', 'true', 'yes', 'on'}


def _typing_actor_for_request(request):
    if request.user.is_authenticated and request.user.is_staff:
        return 'operator'
    return 'user'


def _typing_cache_key(session_id, actor):
    return f'support.typing.{int(session_id)}.{actor}'


def _set_typing_state(session_id, actor, is_typing):
    key = _typing_cache_key(session_id, actor)
    if is_typing:
        cache.set(key, 1, timeout=TYPING_TIMEOUT_SECONDS)
    else:
        cache.delete(key)


def _get_typing_state(session_id, actor):
    return bool(cache.get(_typing_cache_key(session_id, actor)))


def _poll_active_lock_key(request, session_id):
    if request.user.is_authenticated:
        client_key = f'user:{request.user.id}'
    else:
        client_key = f'ip:{_client_ip(request) or "unknown"}'
    return f'{POLL_ACTIVE_LOCK_PREFIX}.{int(session_id)}.{client_key}'


def _poll_signature_key(session_id):
    return f'{POLL_SIGNATURE_PREFIX}.{int(session_id)}'


def _touch_poll_signature(session_id, latest_message_id=0):
    signature = f'{int(latest_message_id)}:{int(time.time() * 1000)}'
    cache.set(_poll_signature_key(session_id), signature, timeout=60 * 60 * 24)
    return signature


def _current_poll_signature(session_id):
    key = _poll_signature_key(session_id)
    signature = cache.get(key)
    if signature:
        return signature
    latest_id = ChatMessage.objects.filter(session_id=session_id).aggregate(max_id=Max('id')).get('max_id') or 0
    return _touch_poll_signature(session_id, latest_id)


def _fetch_serialized_messages(session, since_id):
    rows = list(
        session.messages.filter(id__gt=since_id).order_by('id').values(
            'id',
            'name',
            'message',
            'is_from_user',
            'created_at',
        )
    )
    messages = [
        {
            'id': row['id'],
            'name': row['name'],
            'message': row['message'],
            'is_from_user': row['is_from_user'],
            'created_at': row['created_at'].isoformat(),
        }
        for row in rows
    ]
    next_since = messages[-1]['id'] if messages else since_id
    return messages, next_since


def _poll_enter(request, session_id, timeout):
    lock_key = _poll_active_lock_key(request, session_id)
    if not cache.add(lock_key, 1, timeout=timeout + 2):
        return None
    try:
        cache.incr(POLL_OPEN_CONNECTIONS_CACHE_KEY)
    except ValueError:
        cache.set(POLL_OPEN_CONNECTIONS_CACHE_KEY, 1, timeout=60 * 60)
    return lock_key, time.monotonic()


def _poll_exit(lock_key, started_at, session_id, delivered):
    if lock_key:
        cache.delete(lock_key)
    latency_ms = int((time.monotonic() - started_at) * 1000)
    cache.set(POLL_LAST_LATENCY_CACHE_KEY, latency_ms, timeout=60 * 60)
    try:
        open_connections = cache.decr(POLL_OPEN_CONNECTIONS_CACHE_KEY)
    except ValueError:
        open_connections = 0
        cache.set(POLL_OPEN_CONNECTIONS_CACHE_KEY, 0, timeout=60 * 60)
    if open_connections < 0:
        open_connections = 0
        cache.set(POLL_OPEN_CONNECTIONS_CACHE_KEY, 0, timeout=60 * 60)
    logger.info(
        '[Support Poll] session_id=%s delivered=%s latency_ms=%s open_connections=%s',
        session_id,
        delivered,
        latency_ms,
        open_connections,
    )


def _can_access_session(request, session):
    if not session:
        return False
    if request.user.is_authenticated and request.user.is_staff:
        return True
    return _is_session_owner(request, session)


def _session_status_meta(session):
    if not session.is_active:
        return 'closed', 'بسته', 'bg-gray-100 text-gray-700'
    last_from_user = getattr(session, 'last_message_from_user', None)
    if last_from_user is True:
        return 'waiting', 'در انتظار پاسخ', 'bg-amber-50 text-amber-700'
    if last_from_user is False:
        return 'answered', 'پاسخ داده شده', 'bg-emerald-50 text-emerald-700'
    return 'open', 'باز', 'bg-sky-50 text-sky-700'


def _session_list_filters():
    return [
        ('all', 'همه'),
        ('open', 'باز'),
        ('waiting', 'در انتظار پاسخ'),
        ('answered', 'پاسخ داده شده'),
        ('closed', 'بسته'),
    ]


def _build_user_session_list(request, contact=None):
    status = (request.GET.get('status') or 'all').strip().lower()
    query = (request.GET.get('q') or '').strip()
    allowed_statuses = {key for key, _ in _session_list_filters()}
    if status not in allowed_statuses:
        status = 'all'

    base_qs = ChatSession.objects.none()
    if request.user.is_authenticated:
        base_qs = ChatSession.objects.filter(user=request.user)
    elif contact:
        base_qs = ChatSession.objects.filter(contact=contact)

    if not base_qs.exists():
        return [], status, query

    latest_message_qs = ChatMessage.objects.filter(session_id=OuterRef('pk')).order_by('-created_at', '-id')
    qs = base_qs.annotate(
        last_message_from_user=Subquery(latest_message_qs.values('is_from_user')[:1]),
        last_message_at=Subquery(latest_message_qs.values('created_at')[:1]),
        unread_count=Count(
            'messages',
            filter=Q(messages__is_from_user=False, messages__read=False),
        ),
    )

    if status == 'open':
        qs = qs.filter(is_active=True)
    elif status == 'waiting':
        qs = qs.filter(is_active=True, last_message_from_user=True)
    elif status == 'answered':
        qs = qs.filter(is_active=True, last_message_from_user=False)
    elif status == 'closed':
        qs = qs.filter(is_active=False)

    if query:
        if query.isdigit():
            qs = qs.filter(id=int(query))
        else:
            qs = qs.filter(
                Q(subject__icontains=query)
                | Q(user_name__icontains=query)
                | Q(user_phone__icontains=query)
            )

    sessions = list(qs.order_by('-created_at')[:10])
    for session in sessions:
        status_key, status_label, status_badge_class = _session_status_meta(session)
        session.status_key = status_key
        session.status_label = status_label
        session.status_badge_class = status_badge_class
    return sessions, status, query


def _operator_queue_filters():
    return [
        ('all', 'همه'),
        ('unread', 'نیازمند پاسخ'),
        ('sla_risk', 'SLA پرریسک'),
        ('mine', 'ارجاع به من'),
        ('unassigned', 'بدون اپراتور'),
    ]


def _operator_queue_sorts():
    return [
        ('priority', 'اولویت پاسخ'),
        ('wait_longest', 'بیشترین انتظار'),
        ('newest', 'جدیدترین'),
        ('oldest', 'قدیمی‌ترین'),
    ]


def _format_wait_duration_fa(seconds):
    seconds = max(0, int(seconds or 0))
    if seconds < 60:
        return f'{seconds} ثانیه'
    minutes = seconds // 60
    if minutes < 60:
        return f'{minutes} دقیقه'
    hours = minutes // 60
    remaining_minutes = minutes % 60
    if hours < 24:
        if remaining_minutes:
            return f'{hours} ساعت و {remaining_minutes} دقیقه'
        return f'{hours} ساعت'
    days = hours // 24
    remaining_hours = hours % 24
    if remaining_hours:
        return f'{days} روز و {remaining_hours} ساعت'
    return f'{days} روز'


def _operator_active_sessions_queryset():
    latest_message_qs = ChatMessage.objects.filter(session_id=OuterRef('pk')).order_by('-created_at', '-id')
    oldest_unread_user_qs = ChatMessage.objects.filter(
        session_id=OuterRef('pk'),
        is_from_user=True,
        read=False,
    ).order_by('created_at', 'id')
    return (
        ChatSession.objects.filter(is_active=True)
        .select_related('contact', 'user', 'assigned_to')
        .annotate(
            unread_count=Count('messages', filter=Q(messages__read=False, messages__is_from_user=True)),
            unread_oldest_at=Subquery(oldest_unread_user_qs.values('created_at')[:1]),
            last_message_at=Subquery(latest_message_qs.values('created_at')[:1]),
            last_message_from_user=Subquery(latest_message_qs.values('is_from_user')[:1]),
        )
    )


def _decorate_operator_sessions(sessions, operator_user, warning_seconds, breach_seconds):
    now = timezone.now()
    for session in sessions:
        wait_anchor = session.unread_oldest_at or session.last_message_at or session.created_at
        wait_seconds = max(0, int((now - wait_anchor).total_seconds())) if wait_anchor else 0
        session.wait_seconds = wait_seconds
        session.wait_duration = _format_wait_duration_fa(wait_seconds)
        session.needs_reply = bool(session.unread_count)
        session.is_mine = bool(operator_user and session.assigned_to_id == operator_user.id)
        session.is_unassigned = session.assigned_to_id is None

        if session.assigned_to_id:
            assignee_name = session.assigned_to.get_full_name() or session.assigned_to.username
            if session.is_mine:
                session.assignment_label = 'ارجاع به من'
                session.assignment_badge_class = 'bg-primary-50 text-primary-700'
            else:
                session.assignment_label = f'ارجاع: {assignee_name}'
                session.assignment_badge_class = 'bg-gray-100 text-gray-700'
        else:
            session.assignment_label = 'بدون اپراتور'
            session.assignment_badge_class = 'bg-violet-50 text-violet-700'

        if session.needs_reply:
            if wait_seconds >= breach_seconds:
                session.priority_rank = 0
                session.priority_label = 'بحرانی'
                session.priority_badge_class = 'bg-red-50 text-red-700'
                session.sla_label = 'SLA نقض شده'
                session.sla_badge_class = 'bg-red-100 text-red-700'
            elif wait_seconds >= warning_seconds:
                session.priority_rank = 1
                session.priority_label = 'فوری'
                session.priority_badge_class = 'bg-amber-50 text-amber-700'
                session.sla_label = 'نزدیک SLA'
                session.sla_badge_class = 'bg-amber-100 text-amber-700'
            else:
                session.priority_rank = 2
                session.priority_label = 'جدید'
                session.priority_badge_class = 'bg-sky-50 text-sky-700'
                session.sla_label = 'در SLA'
                session.sla_badge_class = 'bg-emerald-50 text-emerald-700'
        else:
            session.priority_rank = 3 if session.is_unassigned else 4
            session.priority_label = 'بدون پیام جدید' if session.is_unassigned else 'در حال پیگیری'
            session.priority_badge_class = 'bg-gray-100 text-gray-700'
            session.sla_label = 'بدون SLA'
            session.sla_badge_class = 'bg-gray-100 text-gray-600'

        if session.last_message_from_user is True:
            session.last_side_label = 'آخرین پیام: کاربر'
            session.last_side_class = 'text-amber-700'
        elif session.last_message_from_user is False:
            session.last_side_label = 'آخرین پیام: اپراتور'
            session.last_side_class = 'text-emerald-700'
        else:
            session.last_side_label = 'بدون پیام'
            session.last_side_class = 'text-gray-500'


def _apply_operator_status_filter(sessions, status, operator_user, warning_seconds):
    if status == 'unread':
        return [session for session in sessions if session.needs_reply]
    if status == 'sla_risk':
        return [
            session for session in sessions
            if session.needs_reply and session.wait_seconds >= warning_seconds
        ]
    if status == 'mine':
        return [session for session in sessions if session.assigned_to_id == operator_user.id]
    if status == 'unassigned':
        return [session for session in sessions if session.assigned_to_id is None]
    return list(sessions)


def _apply_operator_sort(sessions, sort_key):
    sessions = list(sessions)
    if sort_key == 'newest':
        sessions.sort(key=lambda session: session.created_at, reverse=True)
        return sessions
    if sort_key == 'oldest':
        sessions.sort(key=lambda session: session.created_at)
        return sessions
    if sort_key == 'wait_longest':
        sessions.sort(key=lambda session: (session.wait_seconds, session.created_at), reverse=True)
        return sessions
    sessions.sort(
        key=lambda session: (
            session.priority_rank,
            -session.wait_seconds,
            session.created_at,
        )
    )
    return sessions


def _operator_quick_replies():
    return [
        {'label': 'در حال بررسی', 'text': 'درخواست شما دریافت شد و در حال بررسی است. نتیجه را همین‌جا اطلاع می‌دهم.'},
        {'label': 'نیاز به زمان', 'text': 'برای بررسی دقیق‌تر به زمان بیشتری نیاز است. حداکثر تا پایان امروز پاسخ نهایی ارسال می‌شود.'},
        {'label': 'تایید انجام شد', 'text': 'بررسی انجام شد و مورد شما با موفقیت ثبت/اعمال شد.'},
        {'label': 'نیاز به اطلاعات', 'text': 'برای ادامه لطفاً شماره سفارش یا جزئیات بیشتر را ارسال کنید.'},
        {'label': 'ارجاع فنی', 'text': 'این مورد به تیم فنی ارجاع شد. پس از دریافت نتیجه اطلاع می‌دهم.'},
        {'label': 'پایان گفتگو', 'text': 'اگر سوال دیگری ندارید، گفتگو را می‌بندم. هر زمان نیاز داشتید می‌توانید دوباره پیام بدهید.'},
    ]


def _support_sla_thresholds():
    warning_default = 5 * 60
    breach_default = 15 * 60
    warning_seconds = warning_default
    breach_seconds = breach_default

    try:
        settings_obj = SiteSettings.load()
    except Exception:
        settings_obj = None

    if settings_obj is not None:
        warning_raw = getattr(settings_obj, 'support_sla_warning_seconds', warning_default)
        breach_raw = getattr(settings_obj, 'support_sla_breach_seconds', breach_default)
        warning_seconds = _parse_non_negative_int(warning_raw, default=warning_default)
        breach_seconds = _parse_non_negative_int(breach_raw, default=breach_default)

    warning_seconds = max(30, warning_seconds)
    breach_seconds = max(60, breach_seconds)
    if breach_seconds <= warning_seconds:
        breach_seconds = warning_seconds + 60
    return warning_seconds, breach_seconds


def _audit_action_label(action):
    labels = {
        SupportAuditLog.ACTION_SEND: 'ارسال پیام',
        SupportAuditLog.ACTION_OPEN: 'باز کردن گفتگو',
        SupportAuditLog.ACTION_CLOSE: 'بستن گفتگو',
        SupportAuditLog.ACTION_SUBSCRIBE: 'فعال‌سازی اعلان',
        SupportAuditLog.ACTION_UNSUBSCRIBE: 'غیرفعال‌سازی اعلان',
        SupportAuditLog.ACTION_PUSH_SUCCESS: 'ارسال موفق اعلان',
        SupportAuditLog.ACTION_PUSH_FAILURE: 'خطای اعلان',
    }
    return labels.get(action, action)


def _build_operator_queue_context(request, *, use_request_filters=True):
    filter_options = _operator_queue_filters()
    sort_options = _operator_queue_sorts()
    allowed_filter_keys = {item[0] for item in filter_options}
    allowed_sort_keys = {item[0] for item in sort_options}

    selected_filter = 'all'
    selected_sort = 'priority'
    query = ''
    if use_request_filters:
        selected_filter = (request.GET.get('status') or 'all').strip().lower()
        selected_sort = (request.GET.get('sort') or 'priority').strip().lower()
        query = (request.GET.get('q') or '').strip()
    if selected_filter not in allowed_filter_keys:
        selected_filter = 'all'
    if selected_sort not in allowed_sort_keys:
        selected_sort = 'priority'

    qs = _operator_active_sessions_queryset()
    if query:
        if query.isdigit():
            qs = qs.filter(
                Q(id=int(query))
                | Q(user_phone__icontains=query)
                | Q(contact__phone__icontains=query)
            )
        else:
            qs = qs.filter(
                Q(user_name__icontains=query)
                | Q(user_phone__icontains=query)
                | Q(subject__icontains=query)
                | Q(contact__name__icontains=query)
                | Q(contact__phone__icontains=query)
            )

    warning_seconds, breach_seconds = _support_sla_thresholds()
    sessions = list(qs)
    _decorate_operator_sessions(
        sessions,
        request.user,
        warning_seconds=warning_seconds,
        breach_seconds=breach_seconds,
    )

    summary_waits = [session.wait_seconds for session in sessions if session.needs_reply]
    summary = {
        'total_active': len(sessions),
        'need_reply': sum(1 for session in sessions if session.needs_reply),
        'critical': sum(1 for session in sessions if session.needs_reply and session.wait_seconds >= breach_seconds),
        'mine': sum(1 for session in sessions if session.assigned_to_id == request.user.id),
        'avg_wait_minutes': int(sum(summary_waits) / len(summary_waits) / 60) if summary_waits else 0,
        'sla_warning_seconds': warning_seconds,
        'sla_breach_seconds': breach_seconds,
        'sla_warning_minutes': (warning_seconds + 59) // 60,
        'sla_breach_minutes': (breach_seconds + 59) // 60,
    }

    sessions = _apply_operator_status_filter(
        sessions,
        selected_filter,
        request.user,
        warning_seconds=warning_seconds,
    )
    sessions = _apply_operator_sort(sessions, selected_sort)

    return {
        'sessions': sessions,
        'selected_filter': selected_filter,
        'selected_sort': selected_sort,
        'query': query,
        'filter_options': filter_options,
        'sort_options': sort_options,
        'summary': summary,
    }

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
    session_list, session_filter, session_query = _build_user_session_list(request, contact=contact)
    action_message, action_message_class = _ticket_action_feedback(request.GET.get('ticket_action'))
    context = {
        'active_session': active_session,
        'closed_unrated_session': closed_unrated_session,
        'contact': contact,
        'form_name': contact.name if contact else '',
        'form_phone': contact.phone if contact else '',
        'form_errors': {},
        'session_list': session_list,
        'session_filter': session_filter,
        'session_query': session_query,
        'session_filters': _session_list_filters(),
        'ticket_action_message': action_message,
        'ticket_action_message_class': action_message_class,
    }
    return render(request, 'support/index.html', context)


@require_POST
@ratelimit(key='ip', rate='10/m', method='POST', block=True)
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
        session_list, session_filter, session_query = _build_user_session_list(request, contact=contact)
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
                'session_list': session_list,
                'session_filter': session_filter,
                'session_query': session_query,
                'session_filters': _session_list_filters(),
            },
            status=400,
        )

    contact, created = SupportContact.objects.get_or_create(
        phone=normalized_phone,
        defaults={
            'name': name,
            'user': request.user if request.user.is_authenticated else None,
        },
    )

    # Privacy guardrail: anonymous users can continue only from the same browser
    # session that started the contact thread (prevents phone-only hijacking).
    session_contact_id = _parse_non_negative_int(request.session.get('support_contact_id'), default=0)
    if (
        not request.user.is_authenticated
        and not created
        and (not session_contact_id or session_contact_id != contact.id)
    ):
        contact_from_state = _resolve_contact_from_request(request)
        session_list, session_filter, session_query = _build_user_session_list(request, contact=contact_from_state)
        return render(
            request,
            'support/index.html',
            {
                'active_session': _session_from_request_state(request),
                'closed_unrated_session': _latest_closed_unrated_session(contact_from_state),
                'contact': contact_from_state,
                'form_name': name,
                'form_phone': phone_raw,
                'form_errors': {
                    'phone': 'برای حفظ حریم خصوصی، ادامه این گفتگو فقط از همان مرورگر قبلی ممکن است.',
                },
                'session_list': session_list,
                'session_filter': session_filter,
                'session_query': session_query,
                'session_filters': _session_list_filters(),
            },
            status=403,
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
    _decorate_session_status(session)
    rating = getattr(session, 'rating', None)
    session_agent = _resolve_session_agent(session)
    can_rate = bool(
        (not session.is_active)
        and (rating is None)
        and session_agent
        and _is_rating_owner(request, session)
    )
    action_message, action_message_class = _ticket_action_feedback(request.GET.get('ticket_action'))
    return render(request, 'support/chat.html', {
        'session': session,
        'messages': messages,
        'contact': session.contact,
        'session_closed': not session.is_active,
        'session_is_owner': _is_session_owner(request, session),
        'can_rate': can_rate,
        'session_rating': rating,
        'ticket_action_message': action_message,
        'ticket_action_message_class': action_message_class,
    })


@require_POST
@ratelimit(key='user_or_ip', rate='20/m', method='POST', block=True)
def send_message(request):
    """Send a customer message while keeping long-polling mode."""
    session_id = request.POST.get('session_id')
    session_token = request.POST.get('session_token')
    message_text = request.POST.get('message', '').strip()

    if not message_text:
        return JsonResponse({'error': 'message required'}, status=400)

    session = _session_from_inputs(session_id=session_id, session_token=session_token, include_closed=True)
    if not session:
        return JsonResponse({'error': 'session not found'}, status=404)

    if not _can_access_session(request, session):
        return JsonResponse({'error': 'forbidden'}, status=403)

    if not session.is_active:
        return JsonResponse({'error': 'session is closed', 'session_closed': True}, status=400)

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
    _touch_poll_signature(session.id, msg.id)
    _set_typing_state(session.id, 'user', False)

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
        'session_token': session.public_token,
    })


@ratelimit(key='user_or_ip', rate='60/m', method='GET', block=True)
def get_messages(request):
    """Bounded long-polling endpoint for retrieving new messages."""
    session_id = request.GET.get('session_id')
    session_token = request.GET.get('session_token')
    last_id = _parse_non_negative_int(request.GET.get('last_id'), default=0)
    timeout = _parse_non_negative_int(request.GET.get('timeout'), default=30)
    timeout = max(1, min(timeout, POLL_MAX_TIMEOUT_SECONDS))

    session = _session_from_inputs(session_id=session_id, session_token=session_token, include_closed=True)
    if not session:
        return JsonResponse({'error': 'session not found'}, status=404)

    if not _can_access_session(request, session):
        return JsonResponse({'error': 'forbidden'}, status=403)

    poll_ctx = _poll_enter(request, session.id, timeout)
    if not poll_ctx:
        return JsonResponse({'error': 'too many concurrent poll requests'}, status=429)

    lock_key, started_at = poll_ctx
    delivered = False
    try:
        poll_signature = _current_poll_signature(session.id)
        while True:
            messages_list, new_last_id = _fetch_serialized_messages(session, last_id)
            if messages_list:
                delivered = True
                return JsonResponse({'messages': messages_list, 'last_id': new_last_id})

            if (time.monotonic() - started_at) >= timeout:
                return JsonResponse({'messages': [], 'last_id': last_id})

            current_signature = _current_poll_signature(session.id)
            if current_signature != poll_signature:
                poll_signature = current_signature
                continue
            time.sleep(POLL_SLEEP_SECONDS)
    finally:
        _poll_exit(lock_key, started_at, session.id, delivered)


@ratelimit(key='user_or_ip', rate='60/m', method='GET', block=True)
def poll_messages(request):
    """Bounded long-polling endpoint compatible with both user and operator views."""
    thread_id = request.GET.get('thread_id') or request.GET.get('session_id')
    thread_token = request.GET.get('thread_token') or request.GET.get('session_token')
    since = _parse_non_negative_int(request.GET.get('since'), default=0)
    timeout = _parse_non_negative_int(request.GET.get('timeout'), default=10)
    timeout = max(1, min(timeout, POLL_MAX_TIMEOUT_SECONDS))

    session = None
    if thread_token or thread_id:
        session = _session_from_inputs(session_id=thread_id, session_token=thread_token, include_closed=True)
        if not session:
            return JsonResponse({'error': 'thread not found'}, status=404)
    else:
        session = _session_from_request_state(request)
        if not session:
            return JsonResponse({'error': 'thread token required or no active session found'}, status=400)

    if not _can_access_session(request, session):
        return JsonResponse({'error': 'forbidden'}, status=403)

    poll_ctx = _poll_enter(request, session.id, timeout)
    if not poll_ctx:
        return JsonResponse({'error': 'too many concurrent poll requests'}, status=429)

    lock_key, started_at = poll_ctx
    delivered = False
    try:
        poll_signature = _current_poll_signature(session.id)
        while True:
            if not ChatSession.objects.filter(id=session.id, is_active=True).exists():
                return JsonResponse({
                    'messages': [],
                    'since': since,
                    'session_closed': True,
                })

            messages_list, next_since = _fetch_serialized_messages(session, since)
            if messages_list:
                delivered = True
                return JsonResponse({
                    'messages': messages_list,
                    'since': next_since,
                    'session_closed': False,
                })

            if (time.monotonic() - started_at) >= timeout:
                return JsonResponse({'messages': [], 'since': since, 'session_closed': False})

            current_signature = _current_poll_signature(session.id)
            if current_signature != poll_signature:
                poll_signature = current_signature
                continue
            time.sleep(POLL_SLEEP_SECONDS)
    finally:
        _poll_exit(lock_key, started_at, session.id, delivered)


@require_POST
def typing_update(request):
    payload = _load_json_payload(request)
    if payload is None:
        return JsonResponse({'error': 'invalid JSON payload'}, status=400)
    payload = payload or {}

    session_id_raw = payload.get('session_id') if 'session_id' in payload else request.POST.get('session_id')
    session_token = (payload.get('session_token') if 'session_token' in payload else request.POST.get('session_token'))
    session = _session_from_inputs(session_id=session_id_raw, session_token=session_token, include_closed=True)
    if not session:
        return JsonResponse({'error': 'session not found'}, status=404)
    if not _can_access_session(request, session):
        return JsonResponse({'error': 'forbidden'}, status=403)

    raw_is_typing = payload.get('is_typing') if 'is_typing' in payload else request.POST.get('is_typing')
    is_typing = _parse_bool(raw_is_typing)
    actor = _typing_actor_for_request(request)
    _set_typing_state(session.id, actor, is_typing)

    return JsonResponse({
        'ok': True,
        'session_id': session.id,
        'session_token': session.public_token,
        'actor': actor,
        'is_typing': is_typing,
    })


@require_http_methods(['GET'])
def typing_status(request):
    session_id = request.GET.get('session_id')
    session_token = request.GET.get('session_token')
    session = _session_from_inputs(session_id=session_id, session_token=session_token, include_closed=True)
    if not session:
        return JsonResponse({'error': 'session not found'}, status=404)
    if not _can_access_session(request, session):
        return JsonResponse({'error': 'forbidden'}, status=403)

    return JsonResponse({
        'ok': True,
        'session_id': session.id,
        'user_typing': _get_typing_state(session.id, 'user'),
        'operator_typing': _get_typing_state(session.id, 'operator'),
    })


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


def user_open_session(request, session_id):
    session = get_object_or_404(ChatSession, id=session_id)
    if not _is_session_owner(request, session):
        return redirect('support:chat')
    _store_session_state(request, session)
    return redirect('support:chat_room')


@require_POST
def user_close_session(request, session_id):
    session = get_object_or_404(ChatSession, id=session_id)
    if not _is_session_owner(request, session):
        return JsonResponse({'error': 'forbidden'}, status=403)

    changed = False
    if session.is_active:
        session.is_active = False
        session.closed_at = timezone.now()
        if request.user.is_authenticated:
            session.closed_by = request.user
            session.save(update_fields=['is_active', 'closed_at', 'closed_by'])
        else:
            session.save(update_fields=['is_active', 'closed_at'])
        _create_audit_log(
            action=SupportAuditLog.ACTION_CLOSE,
            request=request,
            session=session,
            metadata={'source': 'user'},
        )
        changed = True

    target = _safe_next_url(request)
    if changed:
        target = _add_or_replace_query_param(target, 'ticket_action', 'closed')
    return redirect(target)


@require_POST
def user_reopen_session(request, session_id):
    session = get_object_or_404(ChatSession, id=session_id)
    if not _is_session_owner(request, session):
        return JsonResponse({'error': 'forbidden'}, status=403)

    changed = False
    if not session.is_active:
        session.is_active = True
        session.closed_at = None
        session.closed_by = None
        session.save(update_fields=['is_active', 'closed_at', 'closed_by'])
        _create_audit_log(
            action=SupportAuditLog.ACTION_OPEN,
            request=request,
            session=session,
            metadata={'source': 'user'},
        )
        changed = True

    _store_session_state(request, session)
    target = _safe_next_url(request)
    if changed:
        target = _add_or_replace_query_param(target, 'ticket_action', 'reopened')
    return redirect(target)


@staff_member_required
def operator_dashboard(request):
    _set_operator_presence(request.user, active_session_id=None)
    queue_context = _build_operator_queue_context(request, use_request_filters=True)
    live_snapshot = _operator_queue_realtime_snapshot()
    return render(request, 'support/operator_dashboard.html', {
        'active_sessions': queue_context['sessions'],
        'queue_filter': queue_context['selected_filter'],
        'queue_sort': queue_context['selected_sort'],
        'queue_query': queue_context['query'],
        'queue_filters': queue_context['filter_options'],
        'queue_sorts': queue_context['sort_options'],
        'queue_summary': queue_context['summary'],
        'unread_count': live_snapshot['unread_count'],
        'operator_queue_signature': live_snapshot['signature'],
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

    queue_context = _build_operator_queue_context(request, use_request_filters=False)
    messages = session.messages.all()[:300]
    last_message_id = session.messages.order_by('-id').values_list('id', flat=True).first() or 0
    quick_replies = _operator_quick_replies()
    audit_logs = list(session.audit_logs.select_related('staff').order_by('-created_at')[:12])
    for log_item in audit_logs:
        log_item.action_label = _audit_action_label(log_item.action)
        if log_item.staff_id:
            log_item.actor_label = log_item.staff.get_full_name() or log_item.staff.username
        else:
            log_item.actor_label = 'سیستم'

    return render(request, 'support/operator_session.html', {
        'session': session,
        'messages': messages,
        'last_message_id': last_message_id,
        'active_sessions': queue_context['sessions'],
        'queue_summary': queue_context['summary'],
        'quick_replies': quick_replies,
        'audit_logs': audit_logs,
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
    _touch_poll_signature(session.id, msg.id)
    _set_typing_state(session.id, 'operator', False)
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
    snapshot = _operator_queue_realtime_snapshot()
    poll_open_connections = _parse_non_negative_int(cache.get(POLL_OPEN_CONNECTIONS_CACHE_KEY), default=0)
    poll_last_latency_ms = _parse_non_negative_int(cache.get(POLL_LAST_LATENCY_CACHE_KEY), default=0)
    response = JsonResponse({
        'ok': True,
        'unread_count': snapshot['unread_count'],
        'active_sessions': snapshot['total_active'],
        'latest_session_id': snapshot['latest_session_id'],
        'latest_message_id': snapshot['latest_message_id'],
        'queue_signature': snapshot['signature'],
        'poll_open_connections': poll_open_connections,
        'poll_last_latency_ms': poll_last_latency_ms,
    })
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    return response


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
        'poll_open_connections': _parse_non_negative_int(cache.get(POLL_OPEN_CONNECTIONS_CACHE_KEY), default=0),
        'poll_last_latency_ms': _parse_non_negative_int(cache.get(POLL_LAST_LATENCY_CACHE_KEY), default=0),
        'last_error': _get_last_push_error(),
    })
