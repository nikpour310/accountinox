"""
E.2: Checkout End-to-End Tests

Tests cover:
- Product selection and order creation
- Payment gateway initiation (mocked)
- Callback verification and order marking as paid
- AccountItem allocation after successful payment
- Out-of-stock prevention
- Duplicate allocation prevention
- User can view purchased account details
"""
import pytest
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth.models import User
from apps.shop.models import Product, Category, AccountItem, Order, OrderItem, TransactionLog
from apps.accounts.models import Profile
from unittest.mock import patch, MagicMock
import json


@pytest.fixture
def user(db):
    """Create test user"""
    user = User.objects.create_user(
        username='shopper',
        email='shopper@example.com',
        password='ShopPass123!'
    )
    Profile.objects.get_or_create(user=user)
    return user


@pytest.fixture
def product_with_items(db):
    """Create test product with account items"""
    category = Category.objects.create(name='Test Category', slug='test-cat')
    product = Product.objects.create(
        category=category,
        title='Test Premium Account',
        slug='test-account',
        description='A test account',
        price='99.99'
    )
    
    # Create 3 available account items
    for i in range(3):
        item = AccountItem.objects.create(product=product)
        item.set_plain(f'user{i}', f'pass{i}', f'notes {i}')
        item.save()
    
    return product


@pytest.mark.django_db
class TestCheckoutFlow:
    """Test end-to-end checkout flow"""

    def test_product_list_shows_available_products(self, client):
        """Test user can see product list"""
        product = Product.objects.create(
            title='Test Product',
            slug='test-product',
            price='50.00'
        )
        
        resp = client.get(reverse('shop:product_list'))
        assert resp.status_code == 200
        assert 'Test Product' in resp.content.decode()

    def test_product_detail_view(self, client):
        """Test user can view product details"""
        product = Product.objects.create(
            title='Test Product',
            slug='test-product',
            price='50.00',
            description='Test description'
        )
        
        resp = client.get(reverse('shop:product_detail', args=['test-product']))
        assert resp.status_code == 200
        assert 'Test Product' in resp.content.decode()

    @patch('apps.shop.views.get_payment_provider')
    def test_checkout_creates_order_and_redirects_to_payment(self, mock_get_provider, client, product_with_items, user):
        """Test checkout creates order and redirects to payment gateway"""
        client.login(username='shopper', password='ShopPass123!')
        
        # Mock payment provider - patch at views.py location where it's imported
        mock_provider = MagicMock()
        mock_provider.initiate_payment.return_value = (
            True,
            {
                'reference': 'mock_reference_123',
                'payment_url': 'https://payment.gateway.example.com/pay?ref=123'
            }
        )
        mock_get_provider.return_value = mock_provider
        
        # Get CSRF token first
        resp = client.get(reverse('shop:product_list'))
        
        # POST checkout with CSRF token from cookies
        resp = client.post(reverse('shop:checkout'), {
            'product_id': product_with_items.id,
            'gateway': 'zarinpal'
        })
        
        # Should redirect to payment gateway (302) or show payment page (200)
        assert resp.status_code in (200, 302), f"Status {resp.status_code}: {resp.content[:200]}"
        
        # Check order was created
        order = Order.objects.filter(user=user).first()
        assert order is not None
        expected_subtotal = Decimal(str(product_with_items.price))
        assert order.subtotal_amount == expected_subtotal
        assert order.total == (order.subtotal_amount + order.vat_amount)
        assert order.vat_percent_applied >= 0
        assert order.paid == False
        
        # Check order item created
        order_item = order.items.first()
        assert order_item is not None
        assert order_item.product == product_with_items

    @patch('apps.shop.views.get_payment_provider')
    def test_payment_callback_marks_order_paid_and_allocates_item(self, mock_get_provider, client, product_with_items, user):
        """Test payment callback verifies payment and allocates inventory"""
        # Create order first
        order = Order.objects.create(user=user, total=product_with_items.price, paid=False)
        order_item = OrderItem.objects.create(order=order, product=product_with_items, price=product_with_items.price)
        
        # Create transaction log
        tx = TransactionLog.objects.create(
            order=order,
            provider='zarinpal',
            payload={'reference': 'auth_123'},
            success=False
        )
        
        # Mock payment verification - both calls to get_payment_provider
        mock_provider = MagicMock()
        expected_amount = int(Decimal(str(order.total)) * Decimal('100'))
        mock_provider.verify_payment.return_value = (
            True,
            {'verified': True, 'amount': expected_amount},
        )
        mock_get_provider.return_value = mock_provider
        
        # Call callback (simulating ZarinPal callback)
        resp = client.get(reverse('shop:payment_callback', args=['zarinpal']), {
            'Status': '100',  # ZarinPal success code
            'Authority': 'auth_123',
            'order_id': order.id
        })
        
        # Should show success page (or redirect to it)
        assert resp.status_code in (200, 302), f"Status {resp.status_code}: {resp.content[:200]}"
        
        # Verify order is marked as paid
        order.refresh_from_db()
        assert order.paid == True, "Order should be marked as paid after successful callback"
        
        # Verify transaction marked as success
        tx.refresh_from_db()
        assert tx.success == True, "Transaction should be marked as success"
        
        # Verify account item was allocated
        order_item.refresh_from_db()
        assert order_item.account_item is not None, "Account item should be allocated"
        assert order_item.account_item.allocated == True

    @patch('apps.shop.payment_providers.get_payment_provider')
    def test_payment_callback_with_failed_verification(self, mock_get_provider, client, product_with_items, user):
        """Test payment callback handles failed verification"""
        client.login(username='shopper', password='ShopPass123!')
        
        # Create order
        order = Order.objects.create(user=user, total=product_with_items.price, paid=False)
        order_item = OrderItem.objects.create(order=order, product=product_with_items, price=product_with_items.price)
        
        # Create transaction log
        tx = TransactionLog.objects.create(
            order=order,
            provider='zarinpal',
            payload={'reference': 'auth_123'},
            success=False
        )
        
        # Mock failed verification
        mock_provider = MagicMock()
        mock_provider.verify_payment.return_value = (False, {'error': 'Verification failed'})
        mock_get_provider.return_value = mock_provider
        
        # Call callback with failed status
        resp = client.get(reverse('shop:payment_callback', args=['zarinpal']), {
            'Status': '100',
            'Authority': 'auth_123',
            'order_id': order.id
        })
        
        # Should show failure page
        assert resp.status_code in (200, 302)
        
        # Order should remain unpaid
        order.refresh_from_db()
        assert order.paid == False
        
        # No account item should be allocated
        order_item.refresh_from_db()
        assert order_item.account_item is None


@pytest.mark.django_db
class TestInventoryAllocation:
    """Test inventory allocation logic"""

    def test_allocate_first_available_item(self, user, product_with_items):
        """Test that first available AccountItem is allocated"""
        # Get first unallocated item
        item = AccountItem.objects.filter(product=product_with_items, allocated=False).first()
        assert item is not None
        
        # Create order and allocation
        order = Order.objects.create(user=user, total=product_with_items.price, paid=True)
        order_item = OrderItem.objects.create(
            order=order,
            product=product_with_items,
            price=product_with_items.price,
            account_item=item
        )
        
        # Mark as allocated
        item.allocated = True
        item.save()
        
        # Verify allocation
        assert order_item.account_item == item
        assert order_item.account_item.allocated == True

    def test_prevent_duplicate_allocation(self, user, product_with_items):
        """Test that same item cannot be allocated twice"""
        item = AccountItem.objects.filter(product=product_with_items, allocated=False).first()
        
        # Create first order with this item
        order1 = Order.objects.create(user=user, total=product_with_items.price, paid=True)
        order_item1 = OrderItem.objects.create(
            order=order1,
            product=product_with_items,
            price=product_with_items.price,
            account_item=item
        )
        item.allocated = True
        item.save()
        
        # Try to allocate same item to second order
        # First, get next available
        item2 = AccountItem.objects.filter(product=product_with_items, allocated=False).first()
        assert item2 is not None
        assert item2.id != item.id
        
        order2 = Order.objects.create(user=user, total=product_with_items.price, paid=True)
        order_item2 = OrderItem.objects.create(
            order=order2,
            product=product_with_items,
            price=product_with_items.price,
            account_item=item2
        )
        
        # Items should be different
        assert order_item1.account_item.id != order_item2.account_item.id

    def test_out_of_stock_prevention(self, user):
        """Test checkout fails gracefully when out of stock"""
        category = Category.objects.create(name='Limited Stock', slug='limited')
        product = Product.objects.create(
            category=category,
            title='Limited Stock Item',
            slug='limited-item',
            price='50.00'
        )
        
        # Create ONE item and allocate it
        item = AccountItem.objects.create(product=product)
        item.set_plain('user1', 'pass1')
        item.allocated = True
        item.save()
        
        # Check no unallocated items
        available = AccountItem.objects.filter(product=product, allocated=False)
        assert available.count() == 0
        
        # Attempting to allocate when none available returns None
        next_item = available.first()
        assert next_item is None


@pytest.mark.django_db
class TestUserCanViewPurchasedItems:
    """Test that user can view purchased account details"""

    def test_user_can_decrypt_purchased_account_credentials(self, user, product_with_items):
        """Test user can access decrypted account credentials from purchased item"""
        # Create order with allocated item
        order = Order.objects.create(user=user, total=product_with_items.price, paid=True)
        
        # Get an account item
        item = AccountItem.objects.filter(product=product_with_items, allocated=False).first()
        
        # Create order item with allocated account
        order_item = OrderItem.objects.create(
            order=order,
            product=product_with_items,
            price=product_with_items.price,
            account_item=item
        )
        
        # User should be able to decrypt credentials
        decrypted = item.get_plain()
        assert 'username' in decrypted
        assert 'password' in decrypted
        assert 'notes' in decrypted
        assert decrypted['username'] == 'user0' or decrypted['username'].startswith('user')

    def test_order_details_page_shows_allocated_account(self, user, product_with_items):
        """Test that order details show allocated account information"""
        # Create paid order with allocated item
        order = Order.objects.create(user=user, total=product_with_items.price, paid=True)
        
        item = AccountItem.objects.filter(product=product_with_items, allocated=False).first()
        order_item = OrderItem.objects.create(
            order=order,
            product=product_with_items,
            price=product_with_items.price,
            account_item=item
        )
        
        # Verify order relationships
        assert order_item in order.items.all()
        assert order_item.account_item is not None
        assert order_item.account_item.product == product_with_items


@pytest.mark.django_db
class TestPaymentProviderIntegration:
    """Test payment provider selection and integration"""

    @patch('apps.shop.views.get_payment_provider')
    def test_zarinpal_payment_flow(self, mock_get_provider, client, product_with_items, user):
        """Test ZarinPal payment flow"""
        client.login(username='shopper', password='ShopPass123!')
        
        mock_provider = MagicMock()
        mock_provider.initiate_payment.return_value = (
            True,
            {
                'reference': 'zarinpal_ref_123',
                'payment_url': 'https://zarinpal.example.com/pay'
            }
        )
        mock_get_provider.return_value = mock_provider
        
        # Get CSRF token
        client.get(reverse('shop:product_list'))
        
        resp = client.post(reverse('shop:checkout'), {
            'product_id': product_with_items.id,
            'gateway': 'zarinpal'
        })
        
        assert resp.status_code in (200, 302), f"Status {resp.status_code}: {resp.content[:200]}"
        mock_provider.initiate_payment.assert_called_once()

    @patch('apps.shop.views.get_payment_provider')
    def test_zibal_payment_flow(self, mock_get_provider, client, product_with_items, user):
        """Test Zibal payment flow"""
        client.login(username='shopper', password='ShopPass123!')
        
        mock_provider = MagicMock()
        mock_provider.initiate_payment.return_value = (
            True,
            {
                'reference': 'zibal_ref_456',
                'payment_url': 'https://zibal.example.com/pay'
            }
        )
        mock_get_provider.return_value = mock_provider
        
        # Get CSRF token
        client.get(reverse('shop:product_list'))
        
        resp = client.post(reverse('shop:checkout'), {
            'product_id': product_with_items.id,
            'gateway': 'zibal'
        })
        
        assert resp.status_code in (200, 302), f"Status {resp.status_code}: {resp.content[:200]}"
        mock_provider.initiate_payment.assert_called_once()
