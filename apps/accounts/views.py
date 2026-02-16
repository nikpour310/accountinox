import logging
import secrets
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils import timezone as dj_timezone
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit
from django.contrib.auth import get_user_model, login

from apps.core.models import SiteSettings
from apps.shop.models import Order, TransactionLog

from .forms import OrderAddressForm, ProfileForm
from .models import OrderAddress, PendingProfileChange, PhoneOTP, Profile
from .sms_providers import get_sms_provider

logger = logging.getLogger(__name__)
PHONE_RE = re.compile(r'^09\d{9}$')


def _site_settings():
    try:
        return SiteSettings.load()
    except Exception:
        return None


def _orders_for_user(user):
    return (
        Order.objects.filter(user=user)
        .prefetch_related('items__product', 'items__account_item')
        .order_by('-created_at')
    )


@login_required
def dashboard(request):
    orders_qs = _orders_for_user(request.user)
    recent_orders = list(orders_qs[:5])
    paid_orders = orders_qs.filter(paid=True)
    total_spent = paid_orders.aggregate(total=Sum('total')).get('total') or 0

    support_sessions = []
    try:
        from apps.support.models import ChatSession

        support_sessions = list(
            ChatSession.objects.filter(user=request.user)
            .select_related('assigned_to')
            .order_by('-created_at')[:4]
        )
    except Exception:
        support_sessions = []

    return render(
        request,
        'accounts/dashboard.html',
        {
            'recent_orders': recent_orders,
            'orders_count': orders_qs.count(),
            'paid_orders_count': paid_orders.count(),
            'pending_orders_count': orders_qs.filter(paid=False).count(),
            'total_spent': total_spent,
            'support_sessions': support_sessions,
        },
    )


@login_required
def order_list(request):
    orders = _orders_for_user(request.user)
    return render(request, 'accounts/order_list.html', {'orders': orders})


@login_required
def order_detail(request, order_id):
    order = get_object_or_404(_orders_for_user(request.user), pk=order_id)
    transactions = TransactionLog.objects.filter(order=order).order_by('-created_at')
    return render(
        request,
        'accounts/order_detail.html',
        {
            'order': order,
            'transactions': transactions,
        },
    )


@login_required
def profile_settings(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=profile, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'پروفایل با موفقیت به‌روزرسانی شد.')
            return redirect('accounts:profile')
        messages.error(request, 'لطفا خطاهای فرم را بررسی کنید.')
    else:
        form = ProfileForm(instance=profile, user=request.user)

    return render(request, 'accounts/profile.html', {'form': form, 'profile': profile})


@login_required
def address_book(request):
    addresses = OrderAddress.objects.filter(user=request.user)
    if request.method == 'POST':
        form = OrderAddressForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            if not addresses.exists():
                address.is_default = True
            address.save()
            messages.success(request, 'نشانی جدید ثبت شد.')
            return redirect('accounts:addresses')
        messages.error(request, 'ثبت نشانی انجام نشد. اطلاعات را بررسی کنید.')
    else:
        form = OrderAddressForm()

    return render(
        request,
        'accounts/addresses.html',
        {
            'addresses': addresses.order_by('-is_default', '-updated_at'),
            'form': form,
        },
    )


@login_required
def edit_address(request, address_id):
    address = get_object_or_404(OrderAddress, pk=address_id, user=request.user)
    if request.method == 'POST':
        form = OrderAddressForm(request.POST, instance=address)
        if form.is_valid():
            form.save()
            messages.success(request, 'نشانی ویرایش شد.')
            return redirect('accounts:addresses')
        messages.error(request, 'ویرایش نشانی انجام نشد.')
    else:
        form = OrderAddressForm(instance=address)
    return render(
        request,
        'accounts/address_form.html',
        {
            'form': form,
            'address': address,
        },
    )


@login_required
@require_POST
def delete_address(request, address_id):
    address = get_object_or_404(OrderAddress, pk=address_id, user=request.user)
    was_default = address.is_default
    address.delete()
    if was_default:
        fallback = OrderAddress.objects.filter(user=request.user).order_by('-updated_at').first()
        if fallback:
            fallback.is_default = True
            fallback.save(update_fields=['is_default', 'updated_at'])
    messages.success(request, 'نشانی حذف شد.')
    return redirect('accounts:addresses')


@login_required
@require_POST
def set_default_address(request, address_id):
    address = get_object_or_404(OrderAddress, pk=address_id, user=request.user)
    if not address.is_default:
        address.is_default = True
        address.save(update_fields=['is_default', 'updated_at'])
        messages.success(request, 'نشانی پیش‌فرض به‌روزرسانی شد.')
    return redirect('accounts:addresses')


# ── Profile Verification (Phone & Email) ──────────────
EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')


@login_required
@require_POST
@ratelimit(key='user', rate='5/m', block=True)
def send_phone_change_code(request):
    """Send an OTP to a new phone number for profile change verification."""
    import json as _json
    try:
        body = _json.loads(request.body)
    except (ValueError, TypeError):
        body = {}
    phone = (body.get('phone') or '').strip()
    if not phone:
        return JsonResponse({'error': 'شماره موبایل الزامی است'}, status=400)
    if not PHONE_RE.match(phone):
        return JsonResponse({'error': 'شماره موبایل معتبر نیست (مثال: 09123456789)'}, status=400)

    # Check if it's the same phone
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if profile.phone == phone:
        return JsonResponse({'error': 'این شماره قبلاً ثبت شده است'}, status=400)

    # Check if phone is used by someone else
    if Profile.objects.filter(phone=phone).exclude(user=request.user).exists():
        return JsonResponse({'error': 'این شماره موبایل قبلاً توسط کاربر دیگری استفاده شده'}, status=400)

    code = f'{secrets.randbelow(900000) + 100000}'

    pending, _ = PendingProfileChange.objects.update_or_create(
        user=request.user, change_type='phone',
        defaults={'new_value': phone},
    )
    pending.set_code(code)
    pending.save()

    settings_obj = _site_settings()
    provider = get_sms_provider(provider_name=(settings_obj.sms_provider if settings_obj else None))
    provider.send_otp(phone, code)

    return JsonResponse({'ok': True})


@login_required
@require_POST
@ratelimit(key='user', rate='10/m', block=True)
def verify_phone_change(request):
    """Verify OTP and apply the phone number change."""
    import json as _json
    try:
        body = _json.loads(request.body)
    except (ValueError, TypeError):
        body = {}
    code = (body.get('code') or '').strip()
    if not code:
        return JsonResponse({'error': 'کد تایید الزامی است'}, status=400)

    try:
        pending = PendingProfileChange.objects.get(user=request.user, change_type='phone')
    except PendingProfileChange.DoesNotExist:
        return JsonResponse({'error': 'درخواست تغییری یافت نشد'}, status=404)

    if pending.is_expired(300):
        pending.delete()
        return JsonResponse({'error': 'کد منقضی شده. لطفاً دوباره تلاش کنید'}, status=400)

    if not pending.check_code(code):
        pending.attempts += 1
        if pending.attempts >= 5:
            pending.delete()
            return JsonResponse({'error': 'تعداد تلاش بیش از حد مجاز. لطفاً دوباره اقدام کنید'}, status=403)
        pending.save()
        return JsonResponse({'error': 'کد تایید نادرست است'}, status=400)

    # Apply the change
    profile, _ = Profile.objects.get_or_create(user=request.user)
    profile.phone = pending.new_value
    profile.save(update_fields=['phone'])
    pending.delete()

    return JsonResponse({'ok': True, 'new_value': profile.phone})


@login_required
@require_POST
@ratelimit(key='user', rate='5/m', block=True)
def send_email_change_code(request):
    """Send a verification code to the new email address."""
    import json as _json
    try:
        body = _json.loads(request.body)
    except (ValueError, TypeError):
        body = {}
    email = (body.get('email') or '').strip().lower()
    if not email:
        return JsonResponse({'error': 'ایمیل الزامی است'}, status=400)
    if not EMAIL_RE.match(email):
        return JsonResponse({'error': 'ایمیل معتبر نیست'}, status=400)

    User = get_user_model()
    if request.user.email and request.user.email.lower() == email:
        return JsonResponse({'error': 'این ایمیل قبلاً ثبت شده است'}, status=400)

    if User.objects.filter(email__iexact=email).exclude(pk=request.user.pk).exists():
        return JsonResponse({'error': 'این ایمیل قبلاً توسط کاربر دیگری استفاده شده'}, status=400)

    code = f'{secrets.randbelow(900000) + 100000}'

    pending, _ = PendingProfileChange.objects.update_or_create(
        user=request.user, change_type='email',
        defaults={'new_value': email},
    )
    pending.set_code(code)
    pending.save()

    # Send email with the code
    from django.core.mail import send_mail
    try:
        send_mail(
            subject='کد تایید تغییر ایمیل',
            message=f'کد تایید شما: {code}\n\nاین کد ۵ دقیقه اعتبار دارد.',
            from_email=None,  # uses DEFAULT_FROM_EMAIL
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception as e:
        logger.error(f'[EmailChange] Failed to send code to {email}: {e}')
        return JsonResponse({'error': 'ارسال ایمیل ناموفق بود. لطفاً دوباره تلاش کنید'}, status=500)

    return JsonResponse({'ok': True})


@login_required
@require_POST
@ratelimit(key='user', rate='10/m', block=True)
def verify_email_change(request):
    """Verify the code and apply the email change."""
    import json as _json
    try:
        body = _json.loads(request.body)
    except (ValueError, TypeError):
        body = {}
    code = (body.get('code') or '').strip()
    if not code:
        return JsonResponse({'error': 'کد تایید الزامی است'}, status=400)

    try:
        pending = PendingProfileChange.objects.get(user=request.user, change_type='email')
    except PendingProfileChange.DoesNotExist:
        return JsonResponse({'error': 'درخواست تغییری یافت نشد'}, status=404)

    if pending.is_expired(300):
        pending.delete()
        return JsonResponse({'error': 'کد منقضی شده. لطفاً دوباره تلاش کنید'}, status=400)

    if not pending.check_code(code):
        pending.attempts += 1
        if pending.attempts >= 5:
            pending.delete()
            return JsonResponse({'error': 'تعداد تلاش بیش از حد مجاز'}, status=403)
        pending.save()
        return JsonResponse({'error': 'کد تایید نادرست است'}, status=400)

    # Apply the change
    request.user.email = pending.new_value
    request.user.save(update_fields=['email'])
    pending.delete()

    return JsonResponse({'ok': True, 'new_value': request.user.email})


# ── OTP Login Page ─────────────────────────────────────
def otp_login_page(request):
    """Render the OTP login/register page."""
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    settings_obj = _site_settings()
    otp_enabled = settings_obj.otp_enabled if settings_obj else True
    if not otp_enabled:
        return redirect('account_login')
    return render(request, 'accounts/otp_login.html', {
        'otp_expiry': settings_obj.otp_expiry_seconds if settings_obj else 120,
        'otp_cooldown': settings_obj.otp_resend_cooldown if settings_obj else 120,
    })


@require_POST
@ratelimit(key='ip', rate='3/m', block=True)
@ratelimit(key='ip', rate='15/d', block=True)
def send_otp(request):
    settings_obj = _site_settings()
    if settings_obj and not settings_obj.otp_enabled:
        return JsonResponse({'error': 'OTP disabled'}, status=403)

    phone = (request.POST.get('phone') or '').strip()
    if not phone:
        return JsonResponse({'error': 'شماره موبایل الزامی است'}, status=400)
    if not PHONE_RE.match(phone):
        return JsonResponse({'error': 'شماره موبایل معتبر نیست (مثال: 09123456789)'}, status=400)

    otp_code = f'{secrets.randbelow(900000) + 100000}'
    otp, created = PhoneOTP.objects.get_or_create(phone=phone)

    cooldown = settings_obj.otp_resend_cooldown if settings_obj else 120
    if not created and not otp.can_resend(cooldown):
        return JsonResponse({'error': 'cooldown'}, status=429)

    otp.set_code(otp_code)
    otp.mark_sent()
    otp.save()

    provider = get_sms_provider(provider_name=(settings_obj.sms_provider if settings_obj else None))
    provider.send_otp(phone, otp_code)
    return JsonResponse({'ok': True})


@require_POST
@ratelimit(key='ip', rate='5/m', block=True)
def verify_otp(request):
    settings_obj = _site_settings()
    if settings_obj and not settings_obj.otp_enabled:
        return JsonResponse({'error': 'OTP disabled'}, status=403)

    phone = request.POST.get('phone')
    code = request.POST.get('code')
    if not phone or not code:
        return JsonResponse({'error': 'phone and code required'}, status=400)
    try:
        otp = PhoneOTP.objects.get(phone=phone)
    except PhoneOTP.DoesNotExist:
        return JsonResponse({'error': 'no otp'}, status=404)

    expiry = settings_obj.otp_expiry_seconds if settings_obj else 120
    if otp.is_expired(expiry):
        return JsonResponse({'error': 'expired'}, status=400)

    if otp.locked_until and dj_timezone.now() < otp.locked_until:
        return JsonResponse({'error': 'locked'}, status=403)

    if otp.check_code(code):
        otp.attempts = 0
        otp.otp_hmac = None
        otp.save()
        return JsonResponse({'ok': True})

    otp.attempts += 1
    max_attempts = settings_obj.otp_max_attempts if settings_obj else 3
    if otp.attempts >= max_attempts:
        otp.locked_until = dj_timezone.now() + timezone.timedelta(
            seconds=(settings_obj.otp_resend_cooldown if settings_obj else 120)
        )
        otp.save()
        return JsonResponse({'error': 'locked'}, status=403)
    otp.save()
    return JsonResponse({'error': 'invalid'}, status=400)


@require_POST
@ratelimit(key='ip', rate='5/m', block=True)
def verify_otp_login(request):
    """Verify OTP and log in or create a user associated with the phone.

    POST params: phone, code
    Returns JSON {ok: True} on success and logs the user in via Django session.
    """
    settings_obj = _site_settings()
    if settings_obj and not settings_obj.otp_enabled:
        return JsonResponse({'error': 'OTP disabled'}, status=403)

    phone = request.POST.get('phone')
    code = request.POST.get('code')
    if not phone or not code:
        return JsonResponse({'error': 'phone and code required'}, status=400)
    try:
        otp = PhoneOTP.objects.get(phone=phone)
    except PhoneOTP.DoesNotExist:
        return JsonResponse({'error': 'no otp'}, status=404)

    expiry = settings_obj.otp_expiry_seconds if settings_obj else 120
    if otp.is_expired(expiry):
        return JsonResponse({'error': 'expired'}, status=400)

    if otp.locked_until and dj_timezone.now() < otp.locked_until:
        return JsonResponse({'error': 'locked'}, status=403)

    if not otp.check_code(code):
        otp.attempts += 1
        max_attempts = settings_obj.otp_max_attempts if settings_obj else 3
        if otp.attempts >= max_attempts:
            otp.locked_until = dj_timezone.now() + timezone.timedelta(
                seconds=(settings_obj.otp_resend_cooldown if settings_obj else 120)
            )
            otp.save()
            return JsonResponse({'error': 'locked'}, status=403)
        otp.save()
        return JsonResponse({'error': 'invalid'}, status=400)

    # OTP valid — reset and authenticate user by phone
    otp.attempts = 0
    otp.otp_hmac = None
    otp.save()

    User = get_user_model()
    # Prefer existing Profile link
    try:
        profile = Profile.objects.get(phone=phone)
        user = profile.user
    except Profile.DoesNotExist:
        # Try to find a user with username==phone
        try:
            user = User.objects.get(username=phone)
        except User.DoesNotExist:
            # Create a new user with unusable password
            user = User.objects.create(username=phone)
            try:
                user.set_unusable_password()
                user.save()
            except Exception:
                pass
        # Ensure profile exists and phone is set
        Profile.objects.get_or_create(user=user, defaults={'phone': phone})

    # Ensure a backend is set when multiple auth backends are configured
    try:
        from django.conf import settings as _dj_settings
        user.backend = _dj_settings.AUTHENTICATION_BACKENDS[0]
    except Exception:
        pass
    # Log the user in via session
    login(request, user)
    return JsonResponse({'ok': True})

