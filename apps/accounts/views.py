import logging
import secrets
import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.db.models import Sum
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils import timezone as dj_timezone
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit
from django.contrib.auth import get_user_model, login

from allauth.account import app_settings as allauth_account_settings
from allauth.account.forms import ResetPasswordForm
from apps.core.models import SiteSettings
from apps.shop.models import Order, TransactionLog

from .forms import OrderAddressForm, ProfileForm
from .models import OrderAddress, PendingProfileChange, PhoneOTP, Profile
from .sms_providers import get_sms_provider

logger = logging.getLogger(__name__)
PHONE_RE = re.compile(r'^09\d{9}$')
GMAIL_DOMAINS = {'gmail.com', 'googlemail.com'}


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


def _google_oauth_ready(request) -> bool:
    try:
        provider_cfg = getattr(settings, 'SOCIALACCOUNT_PROVIDERS', {}).get('google', {})
        app_cfg = provider_cfg.get('APP') or {}
        env_ready = bool(str(app_cfg.get('client_id', '')).strip() and str(app_cfg.get('secret', '')).strip())
        if env_ready:
            return True
    except Exception:
        pass

    try:
        from allauth.socialaccount.models import SocialApp
        from django.contrib.sites.models import Site

        current_site = Site.objects.get_current(request)
        return SocialApp.objects.filter(provider='google', sites=current_site).exists()
    except Exception:
        return False


def _find_user_by_phone(phone: str):
    profile = Profile.objects.select_related('user').filter(phone=phone).first()
    if profile:
        return profile.user
    User = get_user_model()
    return User.objects.filter(username=phone).first()


def _mask_phone(phone: str) -> str:
    if not phone or len(phone) < 7:
        return phone
    return f'{phone[:4]}***{phone[-3:]}'


def _password_reset_session_clear(request):
    request.session.pop('pwd_reset_phone', None)
    request.session.pop('pwd_reset_user_id', None)
    request.session.modified = True


@ratelimit(key='ip', rate='10/m', block=True)
@ratelimit(key='ip', rate='40/d', block=True)
def smart_password_reset(request):
    """
    Smart password reset entry:
    - phone number -> OTP reset flow
    - gmail -> redirect to Google OAuth login
    - other email -> allauth email code reset flow
    """
    identifier = ''
    if request.method == 'POST':
        identifier = (request.POST.get('identifier') or request.POST.get('email') or '').strip()
        if not identifier:
            messages.error(request, 'شماره موبایل یا ایمیل را وارد کنید.')
            return render(request, 'account/password_reset.html', {'identifier': identifier})

        if PHONE_RE.match(identifier):
            settings_obj = _site_settings()
            if settings_obj and not settings_obj.otp_enabled:
                messages.error(request, 'بازیابی با کد پیامکی موقتاً غیرفعال است.')
                return render(request, 'account/password_reset.html', {'identifier': identifier})

            user = _find_user_by_phone(identifier)
            if not user:
                messages.error(request, 'کاربری با این شماره موبایل پیدا نشد.')
                return render(request, 'account/password_reset.html', {'identifier': identifier})

            code = f'{secrets.randbelow(900000) + 100000}'
            otp, created = PhoneOTP.objects.get_or_create(phone=identifier)
            cooldown = settings_obj.otp_resend_cooldown if settings_obj else 120
            if not created and not otp.can_resend(cooldown):
                seconds_left = max(1, int(cooldown - (dj_timezone.now() - otp.last_sent_at).total_seconds()))
                messages.warning(request, f'ارسال مجدد کد فعلاً ممکن نیست. {seconds_left} ثانیه دیگر تلاش کنید.')
                request.session['pwd_reset_phone'] = identifier
                request.session['pwd_reset_user_id'] = user.id
                request.session.modified = True
                return redirect('account_reset_password_phone_verify')

            otp.set_code(code)
            otp.mark_sent()
            otp.save()
            provider = get_sms_provider(provider_name=(settings_obj.sms_provider if settings_obj else None))
            provider.send_otp(identifier, code)

            request.session['pwd_reset_phone'] = identifier
            request.session['pwd_reset_user_id'] = user.id
            request.session.modified = True
            messages.success(request, 'کد تایید به شماره شما ارسال شد.')
            return redirect('account_reset_password_phone_verify')

        email = identifier.lower()
        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, 'فرمت ورودی معتبر نیست. ایمیل یا شماره موبایل درست وارد کنید.')
            return render(request, 'account/password_reset.html', {'identifier': identifier})

        domain = email.split('@', 1)[1].lower() if '@' in email else ''
        if domain in GMAIL_DOMAINS:
            settings_obj = _site_settings()
            google_enabled = bool(settings_obj.google_oauth_enabled) if settings_obj else False
            if not google_enabled:
                messages.error(request, 'ورود با گوگل در حال حاضر فعال نیست.')
                return render(request, 'account/password_reset.html', {'identifier': identifier})
            if not _google_oauth_ready(request):
                messages.error(request, 'تنظیمات ورود با گوگل کامل نیست. با پشتیبانی تماس بگیرید.')
                return render(request, 'account/password_reset.html', {'identifier': identifier})
            messages.info(request, 'برای حساب‌های Gmail از ورود با گوگل استفاده کنید.')
            return redirect(f"{reverse('google_login')}?process=login")

        reset_form = ResetPasswordForm(data={'email': email})
        if reset_form.is_valid():
            reset_form.save(request)
            if allauth_account_settings.PASSWORD_RESET_BY_CODE_ENABLED:
                messages.success(request, 'کد تایید به ایمیل شما ارسال شد.')
                return redirect('account_confirm_password_reset_code')
            messages.success(request, 'لینک بازیابی رمز عبور به ایمیل شما ارسال شد.')
            return redirect('account_reset_password_done')

        email_errors = reset_form.errors.get('email') or reset_form.non_field_errors()
        if email_errors:
            messages.error(request, email_errors[0])
        else:
            messages.error(request, 'ارسال درخواست بازیابی انجام نشد.')

    return render(request, 'account/password_reset.html', {'identifier': identifier})


@ratelimit(key='ip', rate='15/m', block=True)
def smart_password_reset_phone_verify(request):
    phone = request.session.get('pwd_reset_phone')
    user_id = request.session.get('pwd_reset_user_id')
    if not phone or not user_id:
        messages.error(request, 'درخواست بازیابی رمز پیامکی معتبر نیست. دوباره شروع کنید.')
        return redirect('account_reset_password')

    User = get_user_model()
    user = User.objects.filter(id=user_id).first()
    if not user:
        _password_reset_session_clear(request)
        messages.error(request, 'حساب کاربری مرتبط پیدا نشد. دوباره تلاش کنید.')
        return redirect('account_reset_password')

    form_data = {'code': '', 'password1': '', 'password2': ''}
    errors = {}
    settings_obj = _site_settings()
    expiry = settings_obj.otp_expiry_seconds if settings_obj else 120

    if request.method == 'POST':
        form_data['code'] = (request.POST.get('code') or '').strip()
        form_data['password1'] = (request.POST.get('password1') or '').strip()
        form_data['password2'] = (request.POST.get('password2') or '').strip()

        if not form_data['code']:
            errors['code'] = 'کد تایید الزامی است.'
        if not form_data['password1']:
            errors['password1'] = 'رمز عبور جدید را وارد کنید.'
        if not form_data['password2']:
            errors['password2'] = 'تکرار رمز عبور جدید الزامی است.'
        if form_data['password1'] and form_data['password2'] and form_data['password1'] != form_data['password2']:
            errors['password2'] = 'رمز عبور و تکرار آن یکسان نیست.'
        if form_data['password1'] and user.check_password(form_data['password1']):
            errors['password1'] = 'شما نمی‌توانید رمز قبلی‌تان را دوباره انتخاب کنید.'
        if form_data['password1'] and 'password1' not in errors:
            try:
                validate_password(form_data['password1'], user=user)
            except ValidationError as exc:
                errors['password1'] = exc.messages[0] if exc.messages else 'رمز عبور جدید معتبر نیست.'

        otp = PhoneOTP.objects.filter(phone=phone).first()
        if not otp:
            errors['code'] = 'ابتدا کد تایید را دریافت کنید.'
        elif otp.locked_until and dj_timezone.now() < otp.locked_until:
            errors['code'] = 'تعداد تلاش بیش از حد مجاز است. چند دقیقه بعد دوباره تلاش کنید.'
        elif otp.is_expired(expiry):
            errors['code'] = 'کد تایید منقضی شده است. کد جدید دریافت کنید.'
        elif form_data['code'] and not otp.check_code(form_data['code']):
            otp.attempts += 1
            max_attempts = settings_obj.otp_max_attempts if settings_obj else 3
            if otp.attempts >= max_attempts:
                otp.locked_until = dj_timezone.now() + timezone.timedelta(
                    seconds=(settings_obj.otp_resend_cooldown if settings_obj else 120)
                )
            otp.save(update_fields=['attempts', 'locked_until'])
            errors['code'] = 'کد تایید واردشده صحیح نیست.'

        if not errors:
            user.set_password(form_data['password1'])
            user.save(update_fields=['password'])
            if otp:
                otp.otp_hmac = None
                otp.attempts = 0
                otp.locked_until = None
                otp.save(update_fields=['otp_hmac', 'attempts', 'locked_until'])
            _password_reset_session_clear(request)
            messages.success(request, 'رمز عبور با موفقیت تغییر کرد. اکنون می‌توانید وارد شوید.')
            return redirect('account_login')

    return render(
        request,
        'account/password_reset_phone_verify.html',
        {
            'phone': phone,
            'masked_phone': _mask_phone(phone),
            'form_data': form_data,
            'errors': errors,
        },
    )


@require_POST
@ratelimit(key='ip', rate='6/m', block=True)
def smart_password_reset_phone_resend(request):
    phone = request.session.get('pwd_reset_phone')
    user_id = request.session.get('pwd_reset_user_id')
    if not phone or not user_id:
        messages.error(request, 'درخواست بازیابی رمز پیامکی معتبر نیست. دوباره شروع کنید.')
        return redirect('account_reset_password')

    user = _find_user_by_phone(phone)
    if not user or str(user.id) != str(user_id):
        _password_reset_session_clear(request)
        messages.error(request, 'حساب کاربری مرتبط پیدا نشد. دوباره تلاش کنید.')
        return redirect('account_reset_password')

    settings_obj = _site_settings()
    cooldown = settings_obj.otp_resend_cooldown if settings_obj else 120
    otp, _ = PhoneOTP.objects.get_or_create(phone=phone)
    if not otp.can_resend(cooldown):
        seconds_left = max(1, int(cooldown - (dj_timezone.now() - otp.last_sent_at).total_seconds()))
        messages.warning(request, f'ارسال مجدد کد فعلاً ممکن نیست. {seconds_left} ثانیه دیگر تلاش کنید.')
        return redirect('account_reset_password_phone_verify')

    code = f'{secrets.randbelow(900000) + 100000}'
    otp.set_code(code)
    otp.mark_sent()
    otp.save()
    provider = get_sms_provider(provider_name=(settings_obj.sms_provider if settings_obj else None))
    provider.send_otp(phone, code)
    messages.success(request, 'کد جدید برای شما ارسال شد.')
    return redirect('account_reset_password_phone_verify')


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
