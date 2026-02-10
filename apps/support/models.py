from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone


class SupportContact(models.Model):
    """Support contact record (deduplicated by phone)."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, unique=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-updated_at']
        permissions = (
            ('can_export_support_contacts', 'Can export support contacts'),
        )

    @staticmethod
    def normalize_phone(phone_raw):
        """Normalize phone to a compact canonical form for de-duplication."""
        digits = ''.join(ch for ch in str(phone_raw or '') if ch.isdigit())
        if digits.startswith('0098'):
            digits = '0' + digits[4:]
        elif digits.startswith('98'):
            digits = '0' + digits[2:]
        elif digits.startswith('9') and len(digits) == 10:
            digits = '0' + digits
        return digits

    def save(self, *args, **kwargs):
        normalized = self.normalize_phone(self.phone)
        if normalized:
            self.phone = normalized
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.phone})"


class ChatSession(models.Model):
    """Chat session between a customer and support staff"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    contact = models.ForeignKey(SupportContact, on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions')
    user_name = models.CharField(max_length=255, blank=True)  # For anonymous users
    user_phone = models.CharField(max_length=20, blank=True, default='')
    user_email = models.EmailField(blank=True)
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_chats')
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='support_assigned_sessions',
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='support_closed_sessions',
    )
    subject = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Chat #{self.id} - {self.user_name or self.user}"

    def close(self):
        self.is_active = False
        self.closed_at = timezone.now()
        self.save(update_fields=['is_active', 'closed_at'])


class ChatMessage(models.Model):
    """Individual message in a chat session"""
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=255, blank=True)  # For anonymous messages
    message = models.TextField()
    is_from_user = models.BooleanField(default=True)  # True=customer, False=operator
    created_at = models.DateTimeField(default=timezone.now)
    read = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Msg {self.id} in Chat #{self.session_id} by {'user' if self.is_from_user else 'op'}"


class SupportPushSubscription(models.Model):
    """Web Push subscription for support operators."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='support_push_subscriptions',
        limit_choices_to={'is_staff': True},
    )
    endpoint = models.TextField()
    p256dh = models.CharField(max_length=512)
    auth = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'endpoint'],
                name='uniq_support_push_user_endpoint',
            ),
        ]
        ordering = ['-updated_at']

    def __str__(self):
        return f"PushSub user={self.user_id} active={self.is_active}"


class SupportOperatorPresence(models.Model):
    """Tracks online status of support operators for push targeting."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='support_presence')
    last_seen_at = models.DateTimeField(default=timezone.now)
    active_session = models.ForeignKey(ChatSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='active_operator_presences')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_seen_at']

    def __str__(self):
        return f"Presence user={self.user_id} active_session={self.active_session_id}"


class SupportAuditLog(models.Model):
    ACTION_SEND = 'send'
    ACTION_CLOSE = 'close'
    ACTION_OPEN = 'open'
    ACTION_SUBSCRIBE = 'subscribe'
    ACTION_UNSUBSCRIBE = 'unsubscribe'
    ACTION_PUSH_SUCCESS = 'push_success'
    ACTION_PUSH_FAILURE = 'push_failure'

    ACTION_CHOICES = (
        (ACTION_SEND, 'Send Message'),
        (ACTION_CLOSE, 'Close Session'),
        (ACTION_OPEN, 'Open Session'),
        (ACTION_SUBSCRIBE, 'Push Subscribe'),
        (ACTION_UNSUBSCRIBE, 'Push Unsubscribe'),
        (ACTION_PUSH_SUCCESS, 'Push Success'),
        (ACTION_PUSH_FAILURE, 'Push Failure'),
    )

    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='support_audit_logs')
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    session = models.ForeignKey(ChatSession, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    ip = models.CharField(max_length=64, blank=True, default='')
    user_agent = models.TextField(blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Audit {self.action} by {self.staff_id} at {self.created_at.isoformat()}"


class SupportRating(models.Model):
    """Customer satisfaction score for a closed support session."""
    session = models.OneToOneField(ChatSession, on_delete=models.CASCADE, related_name='rating')
    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='support_ratings',
        limit_choices_to={'is_staff': True},
    )
    score = models.PositiveSmallIntegerField()
    reason = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(score__gte=1, score__lte=5),
                name='support_rating_score_between_1_5',
            ),
        ]
        permissions = (
            ('view_all_support_ratings', 'Can view all support ratings'),
        )

    def clean(self):
        if self.score < 1 or self.score > 5:
            raise ValidationError({'score': 'امتیاز باید بین 1 تا 5 باشد.'})
        if self.score == 1 and not (self.reason or '').strip():
            raise ValidationError({'reason': 'برای امتیاز 1 ثبت دلیل الزامی است.'})
        if self.session_id and self.session.is_active:
            raise ValidationError({'session': 'فقط برای گفتگوی بسته می‌توان امتیاز ثبت کرد.'})
        if self.agent_id and not getattr(self.agent, 'is_staff', False):
            raise ValidationError({'agent': 'امتیاز باید به اپراتور ثبت شود.'})

    def save(self, *args, **kwargs):
        if self.session_id and not self.agent_id:
            self.agent = self.session.assigned_to or self.session.operator or self.session.closed_by
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Rating session={self.session_id} score={self.score}'
