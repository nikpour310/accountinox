from decimal import Decimal
import logging

from django.conf import settings
from django.contrib import messages
from django.db import models
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.models import OrderAddress, Profile

from .models import AccountItem, CartItem, Order, OrderItem, Product, ProductVariant, ProductRegion, TransactionLog
from .notifications import notify_order_success
from .payment_providers import get_payment_provider
from .models import Service

logger = logging.getLogger('shop.payment')
CART_SESSION_KEY = 'cart'
CART_CREDENTIALS_KEY = 'cart_credentials'
CART_OPTIONS_KEY = 'cart_options'  # variant_id, region_id per product
MAX_CART_QTY = 10


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _sync_cart_to_db(request):
    """Save session cart to DB for the logged-in user."""
    if not request.user.is_authenticated:
        return
    cart = _get_cart(request)
    creds = request.session.get(CART_CREDENTIALS_KEY, {})
    options = request.session.get(CART_OPTIONS_KEY, {})
    for pid_str, qty in cart.items():
        pid = _safe_int(pid_str, 0)
        if pid <= 0 or qty <= 0:
            continue
        product_creds = creds.get(pid_str, {})
        product_opts = options.get(pid_str, {})
        variant_id = _safe_int(product_opts.get('variant_id'), None)
        region_id = _safe_int(product_opts.get('region_id'), None)
        CartItem.objects.update_or_create(
            user=request.user, product_id=pid,
            defaults={
                'quantity': qty,
                'variant_id': variant_id,
                'region_id': region_id,
                'customer_email': product_creds.get('email', ''),
                'customer_password': product_creds.get('password', ''),
            },
        )
    # Remove DB items not in session cart
    if cart:
        CartItem.objects.filter(user=request.user).exclude(
            product_id__in=[int(k) for k in cart.keys()]
        ).delete()
    else:
        CartItem.objects.filter(user=request.user).delete()


def _load_cart_from_db(request):
    """Load DB cart into session for the logged-in user (merge with existing session cart)."""
    if not request.user.is_authenticated:
        return
    session_cart = _get_cart(request)
    session_creds = request.session.get(CART_CREDENTIALS_KEY, {})
    session_opts = request.session.get(CART_OPTIONS_KEY, {})
    db_items = CartItem.objects.filter(user=request.user).select_related('product', 'variant', 'region')
    for item in db_items:
        pid_str = str(item.product_id)
        if pid_str not in session_cart:
            session_cart[pid_str] = min(item.quantity, MAX_CART_QTY)
            if item.customer_email or item.customer_password:
                session_creds[pid_str] = {
                    'email': item.customer_email,
                    'password': item.customer_password,
                }
            opts = {}
            if item.variant_id:
                opts['variant_id'] = item.variant_id
            if item.region_id:
                opts['region_id'] = item.region_id
            if opts:
                session_opts[pid_str] = opts
    _save_cart(request, session_cart)
    if session_creds:
        request.session[CART_CREDENTIALS_KEY] = session_creds
        request.session.modified = True
    if session_opts:
        request.session[CART_OPTIONS_KEY] = session_opts
        request.session.modified = True
    # Now sync merged cart back to DB
    _sync_cart_to_db(request)


def _get_cart(request):
    raw_cart = request.session.get(CART_SESSION_KEY, {})
    if not isinstance(raw_cart, dict):
        raw_cart = {}
    cart = {}
    for product_id, quantity in raw_cart.items():
        product_id_int = _safe_int(product_id, 0)
        quantity_int = _safe_int(quantity, 0)
        if product_id_int > 0 and quantity_int > 0:
            cart[str(product_id_int)] = min(quantity_int, MAX_CART_QTY)
    return cart


def _save_cart(request, cart):
    request.session[CART_SESSION_KEY] = cart
    request.session.modified = True


def _build_cart_lines(request):
    cart = _get_cart(request)
    if not cart:
        return [], Decimal('0'), 0

    product_ids = [int(pid) for pid in cart.keys()]
    products = Product.objects.filter(id__in=product_ids)
    product_map = {product.id: product for product in products}
    options = request.session.get(CART_OPTIONS_KEY, {})

    # Preload variants and regions
    variant_ids = [opts.get('variant_id') for opts in options.values() if opts.get('variant_id')]
    region_ids = [opts.get('region_id') for opts in options.values() if opts.get('region_id')]
    variant_map = {}
    region_map = {}
    if variant_ids:
        for v in ProductVariant.objects.filter(id__in=variant_ids):
            variant_map[v.id] = v
    if region_ids:
        for r in ProductRegion.objects.filter(id__in=region_ids):
            region_map[r.id] = r

    lines = []
    subtotal = Decimal('0')
    total_quantity = 0
    normalized_cart = {}

    for product_id_str, quantity in cart.items():
        product = product_map.get(int(product_id_str))
        if not product:
            continue

        product_opts = options.get(product_id_str, {})
        variant = variant_map.get(_safe_int(product_opts.get('variant_id'), 0))
        region = region_map.get(_safe_int(product_opts.get('region_id'), 0))

        # Use variant price if available, else base price
        unit_price = variant.price if variant else product.price
        line_total = unit_price * quantity
        subtotal += line_total
        total_quantity += quantity
        normalized_cart[product_id_str] = quantity
        lines.append(
            {
                'product': product,
                'variant': variant,
                'region': region,
                'unit_price': unit_price,
                'quantity': quantity,
                'line_total': line_total,
            }
        )

    if normalized_cart != cart:
        _save_cart(request, normalized_cart)

    return lines, subtotal, total_quantity


def _checkout_initial_data(request):
    initial = {
        'full_name': '',
        'phone': '',
        'email': '',
        'address_text': '',
        'address_id': '',
        'gateway': 'zarinpal',
    }

    if request.user.is_authenticated:
        profile, _ = Profile.objects.get_or_create(user=request.user)
        default_address = (
            OrderAddress.objects.filter(user=request.user)
            .order_by('-is_default', '-updated_at')
            .first()
        )
        initial['full_name'] = request.user.get_full_name().strip()
        initial['phone'] = (profile.phone or '').strip()
        initial['email'] = (request.user.email or '').strip()
        if default_address:
            initial['address_text'] = (
                f'{default_address.province}، {default_address.city}، {default_address.street_address}'
            )
            initial['address_id'] = str(default_address.id)

    return initial


def product_list(request):
    products = Product.objects.filter(is_active=True).select_related('category', 'service')[:20]
    return render(request, 'shop/product_list.html', {'products': products})


def service_list(request):
    services = Service.objects.filter(active=True).annotate(
        products_count=Count('products', filter=models.Q(products__is_active=True))
    ).order_by('order', 'name')
    return render(request, 'shop/services_list.html', {'services': services})


def service_detail(request, slug):
    service = get_object_or_404(Service, slug=slug, active=True)
    products = service.products.filter(is_active=True).select_related('category')[:50]
    other_services = Service.objects.filter(active=True).exclude(pk=service.pk).annotate(
        products_count=Count('products', filter=models.Q(products__is_active=True))
    ).order_by('order', 'name')[:6]

    # Price range for hero badges
    prices = [p.price for p in products]
    min_price = min(prices) if prices else 0
    max_price = max(prices) if prices else 0

    # Count delivery types
    digital_count = sum(1 for p in products if p.delivery_type == Product.DELIVERY_DIGITAL)
    manual_count = len(products) - digital_count

    return render(request, 'shop/service_detail.html', {
        'service': service,
        'products': products,
        'other_services': other_services,
        'min_price': min_price,
        'max_price': max_price,
        'digital_count': digital_count,
        'manual_count': manual_count,
    })


def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug)
    variants = list(product.active_variants) if product.has_variants else []
    regions = list(product.active_regions) if product.has_regions else []
    return render(request, 'shop/product_detail.html', {
        'product': product,
        'variants': variants,
        'regions': regions,
    })


@require_POST
def cart_add(request):
    product_id = _safe_int(request.POST.get('product_id'), 0)
    quantity = _safe_int(request.POST.get('quantity'), 1)
    quantity = max(1, min(quantity, MAX_CART_QTY))
    variant_id = _safe_int(request.POST.get('variant_id'), 0) or None
    region_id = _safe_int(request.POST.get('region_id'), 0) or None

    product = get_object_or_404(Product, id=product_id)
    if not product.is_available:
        messages.error(request, f'«{product.title}» در حال حاضر ناموجود است.')
        next_url = (request.POST.get('next') or '').strip()
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            return redirect(next_url)
        return redirect('shop:cart')

    # Validate variant if product has variants
    variant = None
    if product.has_variants:
        if variant_id:
            variant = ProductVariant.objects.filter(id=variant_id, product=product, is_active=True).first()
        if not variant:
            messages.error(request, 'لطفاً یک تنوع را انتخاب کنید.')
            return redirect(product.get_absolute_url())

    # Validate region if product has regions
    region = None
    if product.has_regions:
        if region_id:
            region = ProductRegion.objects.filter(id=region_id, product=product, is_active=True).first()
        if not region:
            messages.error(request, 'لطفاً ریجن را انتخاب کنید.')
            return redirect(product.get_absolute_url())

    # If product doesn't allow quantity, force 1
    if not product.allow_quantity:
        quantity = 1

    cart = _get_cart(request)
    current_quantity = cart.get(str(product.id), 0)
    cart[str(product.id)] = min(current_quantity + quantity, MAX_CART_QTY)
    _save_cart(request, cart)

    # Store variant/region selection
    opts = request.session.get(CART_OPTIONS_KEY, {})
    product_opts = {}
    if variant:
        product_opts['variant_id'] = variant.id
    if region:
        product_opts['region_id'] = region.id
    if product_opts:
        opts[str(product.id)] = product_opts
    else:
        opts.pop(str(product.id), None)
    request.session[CART_OPTIONS_KEY] = opts
    request.session.modified = True

    # Store customer credentials if product requires them
    cust_email = (request.POST.get('customer_email') or '').strip()
    cust_password = (request.POST.get('customer_password') or '').strip()
    if cust_email or cust_password:
        creds = request.session.get(CART_CREDENTIALS_KEY, {})
        creds[str(product.id)] = {
            'email': cust_email,
            'password': cust_password,
        }
        request.session[CART_CREDENTIALS_KEY] = creds
        request.session.modified = True

    _sync_cart_to_db(request)
    messages.success(request, f'«{product.title}» به سبد خرید اضافه شد.')

    next_url = (request.POST.get('next') or '').strip()
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect('shop:cart')


def cart_detail(request):
    _load_cart_from_db(request)
    lines, subtotal, total_quantity = _build_cart_lines(request)
    return render(
        request,
        'shop/cart.html',
        {
            'cart_lines': lines,
            'subtotal': subtotal,
            'final_total': subtotal,
            'total_quantity': total_quantity,
        },
    )


@require_POST
def cart_update(request):
    cart = _get_cart(request)
    options = request.session.get(CART_OPTIONS_KEY, {})
    remove_id = _safe_int(request.POST.get('remove_id'), 0)
    if remove_id:
        cart.pop(str(remove_id), None)
        options.pop(str(remove_id), None)
        _save_cart(request, cart)
        request.session[CART_OPTIONS_KEY] = options
        _sync_cart_to_db(request)
        messages.success(request, 'آیتم از سبد خرید حذف شد.')
        return redirect('shop:cart')

    for product_id in list(cart.keys()):
        field_name = f'qty_{product_id}'
        if field_name not in request.POST:
            continue
        quantity = _safe_int(request.POST.get(field_name), 0)
        if quantity <= 0:
            cart.pop(product_id, None)
            options.pop(product_id, None)
        else:
            cart[product_id] = min(quantity, MAX_CART_QTY)
    _save_cart(request, cart)
    request.session[CART_OPTIONS_KEY] = options
    _sync_cart_to_db(request)
    messages.success(request, 'سبد خرید به‌روزرسانی شد.')
    return redirect('shop:cart')


@require_POST
def cart_remove(request, product_id):
    cart = _get_cart(request)
    cart.pop(str(product_id), None)
    options = request.session.get(CART_OPTIONS_KEY, {})
    options.pop(str(product_id), None)
    request.session[CART_OPTIONS_KEY] = options
    _save_cart(request, cart)
    _sync_cart_to_db(request)
    messages.success(request, 'آیتم از سبد خرید حذف شد.')
    return redirect('shop:cart')


@require_http_methods(['GET', 'POST'])
def checkout(request):
    legacy_product = None
    legacy_quantity = _safe_int(request.POST.get('quantity'), 1) if request.method == 'POST' else 1
    legacy_variant = None
    legacy_region = None
    if request.method == 'POST' and request.POST.get('product_id'):
        legacy_product = get_object_or_404(Product, id=request.POST.get('product_id'))
        legacy_quantity = max(1, min(legacy_quantity, MAX_CART_QTY))
        if not legacy_product.allow_quantity:
            legacy_quantity = 1

        # Handle variant/region for quick buy
        qb_variant_id = _safe_int(request.POST.get('variant_id'), 0)
        qb_region_id = _safe_int(request.POST.get('region_id'), 0)
        if qb_variant_id:
            legacy_variant = ProductVariant.objects.filter(
                id=qb_variant_id, product=legacy_product, is_active=True
            ).first()
        if qb_region_id:
            legacy_region = ProductRegion.objects.filter(
                id=qb_region_id, product=legacy_product, is_active=True
            ).first()

        # Store quick-buy credentials in session for later
        qb_email = (request.POST.get('customer_email') or '').strip()
        qb_password = (request.POST.get('customer_password') or '').strip()
        if qb_email or qb_password:
            creds = request.session.get(CART_CREDENTIALS_KEY, {})
            creds[str(legacy_product.id)] = {'email': qb_email, 'password': qb_password}
            request.session[CART_CREDENTIALS_KEY] = creds
            request.session.modified = True

    cart_lines, subtotal, total_quantity = _build_cart_lines(request)
    if legacy_product:
        unit_price = legacy_variant.price if legacy_variant else legacy_product.price
        cart_lines = [
            {
                'product': legacy_product,
                'variant': legacy_variant,
                'region': legacy_region,
                'unit_price': unit_price,
                'quantity': legacy_quantity,
                'line_total': unit_price * legacy_quantity,
            }
        ]
        subtotal = cart_lines[0]['line_total']
        total_quantity = legacy_quantity

    addresses = []
    if request.user.is_authenticated:
        addresses = list(OrderAddress.objects.filter(user=request.user).order_by('-is_default', '-updated_at'))

    if request.method == 'GET':
        initial_data = _checkout_initial_data(request)
        return render(
            request,
            'shop/checkout.html',
            {
                'cart_lines': cart_lines,
                'subtotal': subtotal,
                'final_total': subtotal,
                'total_quantity': total_quantity,
                'addresses': addresses,
                'checkout_data': initial_data,
                'form_errors': {},
            },
        )

    if not cart_lines:
        messages.error(request, 'سبد خرید شما خالی است.')
        return redirect('shop:cart')

    checkout_data = {
        'full_name': (request.POST.get('full_name') or '').strip(),
        'phone': (request.POST.get('phone') or '').strip(),
        'email': (request.POST.get('email') or '').strip(),
        'address_text': (request.POST.get('address_text') or '').strip(),
        'address_id': (request.POST.get('address_id') or '').strip(),
        'gateway': (request.POST.get('gateway') or 'zarinpal').strip(),
    }
    if checkout_data['gateway'] not in {'zarinpal', 'zibal'}:
        checkout_data['gateway'] = 'zarinpal'

    selected_address = None
    if request.user.is_authenticated and checkout_data['address_id']:
        selected_address = OrderAddress.objects.filter(
            user=request.user,
            id=_safe_int(checkout_data['address_id'], 0),
        ).first()
    if selected_address:
        checkout_data['full_name'] = checkout_data['full_name'] or selected_address.full_name
        checkout_data['phone'] = checkout_data['phone'] or selected_address.phone
        if not checkout_data['address_text']:
            checkout_data['address_text'] = (
                f'{selected_address.province}، {selected_address.city}، {selected_address.street_address}'
            )

    if legacy_product:
        checkout_data['full_name'] = checkout_data['full_name'] or (
            request.user.get_full_name().strip() if request.user.is_authenticated else 'خریدار'
        )
        checkout_data['phone'] = checkout_data['phone'] or 'نامشخص'
        checkout_data['address_text'] = checkout_data['address_text'] or 'خرید مستقیم از صفحه محصول'

    form_errors = {}
    if not legacy_product:
        if not checkout_data['full_name']:
            form_errors['full_name'] = 'نام تحویل‌گیرنده را وارد کنید.'
        if not checkout_data['phone']:
            form_errors['phone'] = 'شماره تماس الزامی است.'
        if not checkout_data['address_text']:
            form_errors['address_text'] = 'آدرس تحویل را وارد کنید.'

    if form_errors:
        return render(
            request,
            'shop/checkout.html',
            {
                'cart_lines': cart_lines,
                'subtotal': subtotal,
                'final_total': subtotal,
                'total_quantity': total_quantity,
                'addresses': addresses,
                'checkout_data': checkout_data,
                'form_errors': form_errors,
            },
            status=400,
        )

    order = Order.objects.create(
        user=request.user if request.user.is_authenticated else None,
        total=subtotal,
        status=Order.STATUS_PENDING_REVIEW,
        customer_name=checkout_data['full_name'],
        customer_phone=checkout_data['phone'],
        customer_email=checkout_data['email'],
        shipping_address=checkout_data['address_text'],
    )
    creds = request.session.get(CART_CREDENTIALS_KEY, {})
    for line in cart_lines:
        product_creds = creds.get(str(line['product'].id), {})
        unit_price = line.get('unit_price', line['product'].price)
        OrderItem.objects.create(
            order=order,
            product=line['product'],
            price=unit_price,
            quantity=line['quantity'],
            variant_name=line['variant'].name if line.get('variant') else '',
            region_name=line['region'].name if line.get('region') else '',
            customer_email=product_creds.get('email', ''),
            customer_password=product_creds.get('password', ''),
        )

    # Clear session data after creating order
    request.session.pop(CART_CREDENTIALS_KEY, None)
    request.session.pop(CART_OPTIONS_KEY, None)
    request.session.modified = True

    gateway_name = checkout_data['gateway']
    merchant_id = getattr(settings, 'ZARINPAL_MERCHANT_ID', '')
    if gateway_name == 'zibal':
        merchant_id = getattr(settings, 'ZIBAL_MERCHANT_ID', '')

    callback_path = reverse('shop:payment_callback', args=[gateway_name])
    site_base_url = getattr(settings, 'SITE_URL', '').strip().rstrip('/')
    if site_base_url:
        callback_url = f'{site_base_url}{callback_path}?order_id={order.id}'
    else:
        callback_url = request.build_absolute_uri(f'{callback_path}?order_id={order.id}')

    provider = get_payment_provider(gateway_name, merchant_id, callback_url)
    success, result = provider.initiate_payment(
        int(order.total * 100),
        order.id,
        description=f'Order #{order.id}',
    )

    if success:
        reference = result.get('reference', '')
        TransactionLog.objects.create(
            order=order,
            provider=gateway_name,
            payload={
                'reference': reference,
                'amount': int(order.total * 100),
                'customer_phone': order.customer_phone,
            },
            success=False,
        )
        if not legacy_product:
            _save_cart(request, {})
            _sync_cart_to_db(request)
        payment_url = result.get('payment_url', '')
        return redirect(payment_url)

    error = result.get('error', 'Payment initiation failed')
    return render(
        request,
        'shop/payment_error.html',
        {
            'error': error,
            'order': order,
        },
        status=400,
    )


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def payment_callback(request, provider):
    gateway_name = provider

    if gateway_name == 'zibal':
        status_code = request.GET.get('status') or request.POST.get('status')
        track_id = request.GET.get('trackId') or request.POST.get('trackId')
        reference = track_id
    else:
        status_code = request.GET.get('Status') or request.POST.get('Status')
        authority = request.GET.get('Authority') or request.POST.get('Authority')
        reference = authority

    order_id_param = request.GET.get('order_id') or request.POST.get('order_id')
    order_id = _safe_int(order_id_param, None)

    logger.info('[Payment Callback] provider=%s status=%s reference=%s', gateway_name, status_code, reference)

    if status_code not in ['100', '0']:
        logger.warning('[Payment Callback] Payment failed at gateway: status=%s', status_code)
        return render(
            request,
            'shop/payment_failed.html',
            {
                'error': f'Payment failed with status {status_code}',
                'reference': reference,
            },
        )

    merchant_id = getattr(settings, 'ZARINPAL_MERCHANT_ID', '')
    if gateway_name == 'zibal':
        merchant_id = getattr(settings, 'ZIBAL_MERCHANT_ID', '')

    provider_obj = get_payment_provider(gateway_name, merchant_id)
    success, verify_result = provider_obj.verify_payment(reference)

    tx = None
    try:
        if order_id is not None:
            tx = (
                TransactionLog.objects.filter(order_id=order_id, provider=gateway_name)
                .order_by('-id')
                .first()
            )

        if not tx and reference:
            tx = (
                TransactionLog.objects.filter(provider=gateway_name, payload__reference=reference)
                .order_by('-id')
                .first()
            )
    except Exception as exc:
        logger.exception('Error finding transaction: %s', exc)

    if not tx:
        tx = TransactionLog.objects.create(
            order_id=order_id,
            provider=gateway_name,
            payload={'reference': reference, 'order_id': order_id, 'verify_result': verify_result},
            success=success,
        )
    else:
        tx.payload = tx.payload or {}
        stored_reference = tx.payload.get('reference')
        if reference and stored_reference and reference != stored_reference:
            tx.payload['reference_mismatch'] = {
                'received': reference,
                'expected': stored_reference,
            }
            tx.payload['verify_result'] = verify_result
            tx.success = False
            tx.save(update_fields=['payload', 'success'])
            logger.warning(
                '[Payment Callback] Reference mismatch provider=%s tx_id=%s order_id=%s received=%s expected=%s',
                gateway_name,
                tx.id,
                tx.order_id,
                reference,
                stored_reference,
            )
            return render(
                request,
                'shop/payment_failed.html',
                {
                    'error': 'Payment reference mismatch',
                    'reference': reference,
                },
                status=400,
            )
        tx.payload['verify_result'] = verify_result
        tx.success = success
        tx.save()

    if success:
        if not tx.order_id:
            logger.warning(
                '[Payment Callback] Verified payment without order mapping provider=%s reference=%s order_id_param=%s tx_id=%s',
                gateway_name,
                reference,
                order_id_param,
                tx.id if tx else None,
            )
            return render(
                request,
                'shop/payment_error.html',
                {
                    'error': 'Verified payment could not be mapped to an order',
                    'reference': reference,
                },
                status=400,
            )
        try:
            order = Order.objects.get(id=tx.order_id)
            order.paid = True
            if order.status not in {Order.STATUS_CONFIRMED, Order.STATUS_DELIVERED}:
                order.status = Order.STATUS_PENDING_REVIEW
            order.save()

            for item in order.items.all():
                if item.account_item:
                    continue
                account_item = AccountItem.objects.filter(product=item.product, allocated=False).first()
                if account_item:
                    account_item.allocated = True
                    account_item.save(update_fields=['allocated'])
                    item.account_item = account_item
                    item.save(update_fields=['account_item'])
                    logger.info('[Payment] Allocated account item %s to order %s', account_item.id, order.id)

            needs_follow_up = order.items.filter(account_item__isnull=True).exists()

            # Send email invoice + SMS notification
            try:
                notify_order_success(order)
            except Exception as notify_exc:
                logger.exception('[Payment] Notification error for order %s: %s', order.order_number, notify_exc)

            return render(
                request,
                'shop/payment_success.html',
                {
                    'order': order,
                    'reference': reference,
                    'needs_follow_up': needs_follow_up,
                },
            )
        except Order.DoesNotExist:
            logger.error('Order %s not found for payment callback', tx.order_id)
            return render(
                request,
                'shop/payment_error.html',
                {
                    'error': 'Order not found',
                    'reference': reference,
                },
                status=404,
            )
        except Exception as exc:
            logger.exception('Error processing payment callback: %s', exc)
            return render(
                request,
                'shop/payment_error.html',
                {
                    'error': f'Error: {exc}',
                    'reference': reference,
                },
                status=500,
            )

    error = verify_result.get('error', 'Payment verification failed')
    logger.warning('[Payment] Verification failed: %s', error)
    return render(
        request,
        'shop/payment_failed.html',
        {
            'error': error,
            'reference': reference,
        },
    )


from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404


@login_required
def order_download(request, order_id, item_id):
    """Allow user to download digital file for a paid order item."""
    order = get_object_or_404(Order, id=order_id, user=request.user, paid=True)
    item = get_object_or_404(OrderItem, id=item_id, order=order)
    if not item.product or item.product.delivery_type != Product.DELIVERY_DIGITAL:
        raise Http404
    if not item.product.digital_file:
        raise Http404
    file_field = item.product.digital_file
    response = FileResponse(file_field.open('rb'), as_attachment=True, filename=file_field.name.split('/')[-1])
    return response
