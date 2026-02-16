from io import BytesIO

from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.db.models import Count, Exists, Max, OuterRef, Subquery, Q
from openpyxl import Workbook
import logging

from .models import (
    ChatMessage,
    ChatSession,
    SupportPushSubscription,
    SupportContact,
    SupportOperatorPresence,
    SupportAuditLog,
    SupportRating,
)

logger = logging.getLogger('apps')


class HasActiveSessionFilter(admin.SimpleListFilter):
    title = 'وضعیت جلسه'
    parameter_name = 'has_active_session'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'دارای جلسه فعال'),
            ('no', 'بدون جلسه فعال'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'yes':
            return queryset.filter(sessions__is_active=True).distinct()
        if value == 'no':
            return queryset.exclude(sessions__is_active=True)
        return queryset


class UnreadSessionFilter(admin.SimpleListFilter):
    title = 'پیام خوانده‌نشده'
    parameter_name = 'has_unread'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'دارای پیام خوانده‌نشده'),
            ('no', 'بدون پیام خوانده‌نشده'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'yes':
            return queryset.filter(messages__is_from_user=True, messages__read=False).distinct()
        if value == 'no':
            return queryset.exclude(messages__is_from_user=True, messages__read=False)
        return queryset


class ChatSessionInline(admin.TabularInline):
    model = ChatSession
    fields = ('id', 'subject', 'assigned_to', 'is_active', 'created_at', 'closed_at')
    readonly_fields = ('id', 'subject', 'assigned_to', 'is_active', 'created_at', 'closed_at')
    show_change_link = True
    extra = 0


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'contact_summary',
        'last_message_snippet',
        'updated_at',
        'unread_count',
        'assigned_badge',
        'active_status',
    )
    list_filter = ('is_active', 'assigned_to', UnreadSessionFilter, 'created_at')
    search_fields = ('user_name', 'user_phone', 'contact__phone', 'user__email', 'user__username')
    readonly_fields = ('created_at', 'closed_at', 'updated_at')
    actions = ('close_selected_sessions',)

    fieldsets = (
        ('اطلاعات جلسه', {
            'fields': ('user', 'contact', 'user_name', 'user_phone', 'user_email', 'subject'),
        }),
        ('اپراتور', {
            'fields': ('operator', 'assigned_to', 'closed_by'),
        }),
        ('وضعیت', {
            'fields': ('is_active', 'updated_at', 'created_at', 'closed_at'),
        }),
    )

    def get_queryset(self, request):
        latest_messages = ChatMessage.objects.filter(session=OuterRef('pk')).order_by('-created_at')
        return (
            super()
            .get_queryset(request)
            .select_related('contact', 'assigned_to', 'closed_by', 'user')
            .annotate(
                unread_count_value=Count(
                    'messages',
                    filter=Q(messages__is_from_user=True, messages__read=False),
                ),
                updated_at_value=Max('messages__created_at'),
                latest_message_value=Subquery(latest_messages.values('message')[:1]),
                latest_message_is_from_user_value=Subquery(latest_messages.values('is_from_user')[:1]),
            )
        )

    def changelist_view(self, request, extra_context=None):
        if self._should_redirect_to_support_inbox(request):
            return HttpResponseRedirect(f'{request.path}?is_active__exact=1&has_unread=yes')
        return super().changelist_view(request, extra_context=extra_context)

    def get_list_display(self, request):
        columns = list(super().get_list_display(request))
        columns.append('open_action')
        if self.has_change_permission(request):
            columns.extend(['take_action', 'close_action'])
        return tuple(columns)

    def get_urls(self):
        custom_urls = [
            path(
                '<path:object_id>/take/',
                self.admin_site.admin_view(self.take_session_view),
                name='support_chatsession_take',
            ),
            path(
                '<path:object_id>/close/',
                self.admin_site.admin_view(self.close_session_view),
                name='support_chatsession_close',
            ),
        ]
        return custom_urls + super().get_urls()

    def _should_redirect_to_support_inbox(self, request):
        if request.method != 'GET':
            return False
        if _is_owner(request.user):
            return False
        if not request.user.groups.filter(name='Support Agent').exists():
            return False
        useful_query_keys = [key for key in request.GET.keys() if key and key != '_changelist_filters']
        return len(useful_query_keys) == 0

    def _redirect_back(self, request):
        return HttpResponseRedirect(
            request.META.get('HTTP_REFERER', reverse('admin:support_chatsession_changelist'))
        )

    def _close_sessions(self, request, queryset):
        open_ids = list(queryset.filter(is_active=True).values_list('id', flat=True))
        if not open_ids:
            return 0, 0

        unread_marked = ChatMessage.objects.filter(
            session_id__in=open_ids,
            is_from_user=True,
            read=False,
        ).update(read=True)
        closed_count = ChatSession.objects.filter(id__in=open_ids, is_active=True).update(
            is_active=False,
            closed_at=timezone.now(),
            closed_by=request.user if request.user.is_authenticated else None,
        )
        return closed_count, unread_marked

    @admin.display(description='مخاطب')
    def contact_summary(self, obj):
        name = ''
        phone = ''
        if obj.contact_id:
            name = (obj.contact.name or '').strip()
            phone = (obj.contact.phone or '').strip()
        if not name:
            name = (obj.user_name or '').strip() or (obj.user.get_username() if obj.user_id else '-')
        if not phone:
            phone = (obj.user_phone or '').strip() or '-'
        return format_html(
            '<div class="inbox-contact"><strong>{}</strong><span>{}</span></div>',
            name,
            phone,
        )

    @admin.display(description='آخرین پیام')
    def last_message_snippet(self, obj):
        text = (getattr(obj, 'latest_message_value', '') or '').strip()
        if not text:
            return '-'
        sender_is_user = bool(getattr(obj, 'latest_message_is_from_user_value', False))
        sender = 'کاربر' if sender_is_user else 'اپراتور'
        badge = 'status-badge--warning' if sender_is_user else 'status-badge--muted'
        short = text if len(text) <= 72 else text[:69] + '...'
        return format_html(
            '<div class="inbox-message"><span class="status-badge {}">{}</span><span>{}</span></div>',
            badge,
            sender,
            short,
        )

    @admin.display(description='وضعیت', ordering='is_active')
    def active_status(self, obj):
        if obj.is_active:
            return format_html('<span class="status-badge status-badge--success">{}</span>', 'فعال')
        return format_html('<span class="status-badge status-badge--muted">{}</span>', 'بسته')

    @admin.display(description='پیام خوانده‌نشده', ordering='unread_count_value')
    def unread_count(self, obj):
        unread = getattr(obj, 'unread_count_value', 0) or 0
        badge = 'status-badge--danger' if unread else 'status-badge--muted'
        return format_html('<span class="status-badge {}">{}</span>', badge, unread)

    @admin.display(description='آخرین به‌روزرسانی', ordering='updated_at_value')
    def updated_at(self, obj):
        return getattr(obj, 'updated_at_value', None) or obj.created_at

    @admin.display(description='اپراتور', ordering='assigned_to__username')
    def assigned_badge(self, obj):
        if obj.assigned_to_id:
            return format_html(
                '<span class="status-badge status-badge--success">{}</span>',
                obj.assigned_to.get_username(),
            )
        return format_html('<span class="status-badge status-badge--muted">{}</span>', 'بدون اپراتور')

    @admin.display(description='باز')
    def open_action(self, obj):
        url = reverse('admin:support_chatsession_change', args=(obj.pk,))
        return format_html('<a class="admin-row-action" href="{}">باز کردن</a>', url)

    @admin.display(description='برداشت')
    def take_action(self, obj):
        if not obj.is_active:
            return '-'
        if obj.assigned_to_id:
            return '-'
        url = reverse('admin:support_chatsession_take', args=(obj.pk,))
        return format_html('<a class="admin-row-action" href="{}">برداشت</a>', url)

    @admin.display(description='بستن')
    def close_action(self, obj):
        if not obj.is_active:
            return '-'
        url = reverse('admin:support_chatsession_close', args=(obj.pk,))
        return format_html('<a class="admin-row-action admin-row-action--danger" href="{}">بستن</a>', url)

    def take_session_view(self, request, object_id):
        session_obj = self.get_object(request, object_id)
        if session_obj is None:
            raise Http404('Session not found.')
        if not self.has_change_permission(request, session_obj):
            raise PermissionDenied('You do not have permission to assign sessions.')
        if not request.user.is_authenticated:
            raise PermissionDenied('Authenticated staff only.')

        changed_fields = []
        if session_obj.assigned_to_id != request.user.id:
            session_obj.assigned_to = request.user
            changed_fields.append('assigned_to')
        if session_obj.operator_id is None:
            session_obj.operator = request.user
            changed_fields.append('operator')

        if changed_fields:
            session_obj.save(update_fields=changed_fields)
            self.message_user(request, 'جلسه به شما واگذار شد.', level=messages.SUCCESS)
        else:
            self.message_user(request, 'جلسه قبلاً به شما واگذار شده است.', level=messages.INFO)
        return self._redirect_back(request)

    def close_session_view(self, request, object_id):
        session_obj = self.get_object(request, object_id)
        if session_obj is None:
            raise Http404('Session not found.')
        if not self.has_change_permission(request, session_obj):
            raise PermissionDenied('You do not have permission to close sessions.')

        closed_count, unread_marked = self._close_sessions(request, ChatSession.objects.filter(pk=session_obj.pk))
        if closed_count:
            self.message_user(
                request,
                f'جلسه بسته شد و {unread_marked} پیام خوانده‌نشده علامت‌گذاری شد.',
                level=messages.SUCCESS,
            )
        else:
            self.message_user(request, 'این جلسه قبلاً بسته شده است.', level=messages.INFO)
        return self._redirect_back(request)

    @admin.action(description='بستن جلسات انتخاب‌شده')
    def close_selected_sessions(self, request, queryset):
        closed_count, unread_marked = self._close_sessions(request, queryset)
        if not closed_count:
            self.message_user(request, 'جلسه فعالی برای بستن انتخاب نشده است.', level=messages.INFO)
            return

        self.message_user(
            request,
            f'{closed_count} جلسه بسته شد و {unread_marked} پیام خوانده‌نشده علامت‌گذاری شد.',
            level=messages.SUCCESS,
        )


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'name', 'is_from_user', 'created_at', 'read')
    list_filter = ('is_from_user', 'read', 'created_at')
    search_fields = ('name', 'message')
    readonly_fields = ('created_at',)
    
    fieldsets = (
        ('محتوای پیام', {
            'fields': ('session', 'message'),
        }),
        ('فرستنده', {
            'fields': ('user', 'name', 'is_from_user'),
        }),
        ('وضعیت', {
            'fields': ('read', 'created_at'),
        }),
    )


@admin.register(SupportPushSubscription)
class SupportPushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_active', 'created_at', 'updated_at')
    search_fields = ('user__username', 'user__email', 'endpoint')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(SupportContact)
class SupportContactAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'normalized_phone',
        'last_session',
        'last_message_at',
        'sessions_count',
        'has_active_session_badge',
        'created_at',
    )
    list_filter = (HasActiveSessionFilter, 'created_at')
    search_fields = ('name', 'phone')
    readonly_fields = ('created_at', 'updated_at', 'last_seen_at')
    inlines = (ChatSessionInline,)
    actions = ('export_contacts_xlsx',)

    def get_queryset(self, request):
        latest_session_subquery = (
            ChatSession.objects
            .filter(contact=OuterRef('pk'))
            .order_by('-created_at')
            .values('id')[:1]
        )
        return (
            super()
            .get_queryset(request)
            .annotate(
                sessions_count_value=Count('sessions', distinct=True),
                last_message_at_value=Max('sessions__messages__created_at'),
                last_session_id_value=Subquery(latest_session_subquery),
                has_active_session_value=Exists(
                    ChatSession.objects.filter(contact=OuterRef('pk'), is_active=True)
                ),
            )
        )

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not self._has_export_permission(request):
            actions.pop('export_contacts_xlsx', None)
        return actions

    def get_urls(self):
        custom_urls = [
            path(
                'export-filtered/',
                self.admin_site.admin_view(self.export_filtered_contacts),
                name='support_supportcontact_export_filtered',
            ),
        ]
        return custom_urls + super().get_urls()

    def _has_export_permission(self, request):
        return bool(
            request.user.is_superuser
            or request.user.has_perm('support.can_export_support_contacts')
        )

    def _export_contacts_queryset(self, queryset, filename):
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = 'Support Contacts'
        worksheet.append(
            [
                'id',
                'name',
                'phone',
                'created_at',
                'last_seen',
                'total_sessions',
                'total_messages_user',
                'total_messages_operator',
                'last_session_status',
                'last_message_at',
            ]
        )

        for contact in queryset.order_by('id').prefetch_related('sessions__messages'):
            sessions = list(contact.sessions.all().order_by('-created_at'))
            total_sessions = len(sessions)
            total_messages_user = 0
            total_messages_operator = 0
            last_message_at = None
            for session in sessions:
                for message in session.messages.all():
                    if message.is_from_user:
                        total_messages_user += 1
                    else:
                        total_messages_operator += 1
                    if not last_message_at or message.created_at > last_message_at:
                        last_message_at = message.created_at

            last_session = sessions[0] if sessions else None
            if last_session is None:
                last_session_status = ''
            else:
                last_session_status = 'active' if last_session.is_active else 'closed'

            worksheet.append(
                [
                    contact.id,
                    contact.name,
                    contact.phone,
                    contact.created_at.isoformat(),
                    contact.last_seen_at.isoformat() if contact.last_seen_at else '',
                    total_sessions,
                    total_messages_user,
                    total_messages_operator,
                    last_session_status,
                    last_message_at.isoformat() if last_message_at else '',
                ]
            )

        stream = BytesIO()
        workbook.save(stream)
        stream.seek(0)
        response = HttpResponse(
            stream.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename={filename}'
        return response

    def export_filtered_contacts(self, request):
        if not self._has_export_permission(request):
            raise PermissionDenied('You do not have permission to export support contacts.')
        changelist = self.get_changelist_instance(request)
        queryset = changelist.get_queryset(request)
        try:
            count = queryset.count()
        except Exception:
            count = None
        logger.info(
            'support:export_filtered contacts',
            extra={
                'user_id': getattr(request.user, 'id', None),
                'username': getattr(request.user, 'username', None),
                'is_superuser': getattr(request.user, 'is_superuser', False),
                'export_count': count,
                'path': request.path,
                'query': request.GET.dict(),
            },
        )
        return self._export_contacts_queryset(queryset, filename='support_contacts_filtered.xlsx')

    @admin.action(description='Export selected contacts to Excel (.xlsx)')
    def export_contacts_xlsx(self, request, queryset):
        if not self._has_export_permission(request):
            raise PermissionDenied('You do not have permission to export support contacts.')
        try:
            count = queryset.count()
        except Exception:
            count = None
        logger.info(
            'support:export selected contacts',
            extra={
                'user_id': getattr(request.user, 'id', None),
                'username': getattr(request.user, 'username', None),
                'is_superuser': getattr(request.user, 'is_superuser', False),
                'export_count': count,
                'path': request.path,
            },
        )
        return self._export_contacts_queryset(queryset, filename='support_contacts.xlsx')

    @admin.display(description='تعداد جلسات', ordering='sessions_count_value')
    def sessions_count(self, obj):
        return getattr(obj, 'sessions_count_value', 0) or 0

    @admin.display(description='تلفن')
    def normalized_phone(self, obj):
        return SupportContact.normalize_phone(obj.phone)

    @admin.display(description='آخرین جلسه', ordering='last_session_id_value')
    def last_session(self, obj):
        session_id = getattr(obj, 'last_session_id_value', None)
        if not session_id:
            return '-'
        url = reverse('admin:support_chatsession_change', args=(session_id,))
        return format_html('<a href="{}">جلسه #{}</a>', url, session_id)

    @admin.display(description='آخرین پیام', ordering='last_message_at_value')
    def last_message_at(self, obj):
        return getattr(obj, 'last_message_at_value', None) or '-'

    @admin.display(description='جلسه فعال', ordering='has_active_session_value')
    def has_active_session_badge(self, obj):
        if getattr(obj, 'has_active_session_value', False):
            return format_html('<span class="status-badge status-badge--success">{}</span>', 'فعال')
        return format_html('<span class="status-badge status-badge--muted">{}</span>', 'ندارد')


@admin.register(SupportOperatorPresence)
class SupportOperatorPresenceAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'active_session', 'last_seen_at', 'updated_at')
    list_filter = ('last_seen_at', 'updated_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(SupportAuditLog)
class SupportAuditLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'action', 'staff', 'session', 'ip', 'created_at')
    list_filter = ('action', 'created_at')
    search_fields = ('staff__username', 'staff__email', 'ip', 'user_agent', 'metadata')
    readonly_fields = ('created_at',)


def _is_owner(user):
    return bool(user and user.is_authenticated and (user.is_superuser or user.groups.filter(name='Owner').exists()))


@admin.register(SupportRating)
class SupportRatingAdmin(admin.ModelAdmin):
    list_display = ('session_link', 'agent', 'score_badge', 'created_at', 'reason_preview')
    list_filter = ('score', 'created_at')
    search_fields = ('session__id', 'agent__username', 'agent__email', 'reason')
    readonly_fields = ('created_at',)

    def get_list_filter(self, request):
        base = list(super().get_list_filter(request))
        if _is_owner(request.user):
            base.append('agent')
        return tuple(base)

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related('session', 'agent')
        if _is_owner(request.user):
            return queryset
        if request.user.is_staff:
            return queryset.filter(agent=request.user)
        return queryset.none()

    def has_view_permission(self, request, obj=None):
        if _is_owner(request.user):
            return True
        return request.user.is_staff

    def has_module_permission(self, request):
        if _is_owner(request.user):
            return True
        return request.user.is_staff

    def has_change_permission(self, request, obj=None):
        return _is_owner(request.user)

    def has_delete_permission(self, request, obj=None):
        return _is_owner(request.user)

    @admin.display(description='امتیاز', ordering='score')
    def score_badge(self, obj):
        score = obj.score
        if score >= 4:
            badge_class = 'status-badge--success'
        elif score == 3:
            badge_class = 'status-badge--warning'
        else:
            badge_class = 'status-badge--danger'
        return format_html('<span class="status-badge {}">{}</span>', badge_class, score)

    @admin.display(description='جلسه', ordering='session__id')
    def session_link(self, obj):
        if not obj.session_id:
            return '-'
        url = reverse('admin:support_chatsession_change', args=(obj.session_id,))
        return format_html('<a href="{}">#{}</a>', url, obj.session_id)

    @admin.display(description='دلیل')
    def reason_preview(self, obj):
        reason = (obj.reason or '').strip()
        if not reason:
            return '-'
        short_reason = reason if len(reason) <= 70 else f'{reason[:67]}...'
        if obj.score == 1:
            return format_html('<span class="rating-reason rating-reason--critical">{}</span>', short_reason)
        return short_reason
