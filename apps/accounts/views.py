from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils import timezone as dj_timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.core.models import SiteSettings
from apps.shop.models import Order, TransactionLog

from .forms import OrderAddressForm, ProfileForm
from .models import OrderAddress, PhoneOTP, Profile
from .sms_providers import get_sms_provider
import random


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

    return render(request, 'accounts/profile.html', {'form': form})


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


@csrf_exempt
@require_POST
@ratelimit(key='ip', rate='5/m', block=True)
def send_otp(request):
    settings_obj = _site_settings()
    if settings_obj and not settings_obj.otp_enabled:
        return JsonResponse({'error': 'OTP disabled'}, status=403)

    phone = request.POST.get('phone')
    if not phone:
        return JsonResponse({'error': 'phone required'}, status=400)

    otp_code = f'{random.randint(100000, 999999)}'
    otp, created = PhoneOTP.objects.get_or_create(phone=phone)

    cooldown = settings_obj.otp_resend_cooldown if settings_obj else 60
    if not created and not otp.can_resend(cooldown):
        return JsonResponse({'error': 'cooldown'}, status=429)

    otp.set_code(otp_code)
    otp.mark_sent()
    otp.save()

    provider = get_sms_provider(provider_name=(settings_obj.sms_provider if settings_obj else None))
    provider.send_sms(phone, f'کد تایید شما: {otp_code}')
    return JsonResponse({'ok': True})


@csrf_exempt
@require_POST
@ratelimit(key='ip', rate='10/m', block=True)
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

    expiry = settings_obj.otp_expiry_seconds if settings_obj else 300
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
    max_attempts = settings_obj.otp_max_attempts if settings_obj else 5
    if otp.attempts >= max_attempts:
        otp.locked_until = dj_timezone.now() + timezone.timedelta(
            seconds=(settings_obj.otp_resend_cooldown if settings_obj else 60)
        )
        otp.save()
        return JsonResponse({'error': 'locked'}, status=403)
    otp.save()
    return JsonResponse({'error': 'invalid'}, status=400)

