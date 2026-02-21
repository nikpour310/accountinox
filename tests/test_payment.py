"""
Tests for payment gateway functionality (ZarinPal/Zibal)
Uses mocking to avoid real API calls
"""
import pytest
import logging
from unittest.mock import patch, MagicMock
from django.test import Client
from django.urls import reverse
from apps.shop.models import Product, Category, Order, OrderItem, AccountItem, TransactionLog
from apps.shop.payment_providers import ZarinPalProvider, ZibalProvider


@pytest.mark.django_db
class TestPaymentGateway:
    
    def setup_method(self):
        """Setup for each test"""
        # Mock merchant IDs for testing
        from django.test import override_settings
        self.settings_context = override_settings(
            ZARINPAL_MERCHANT_ID='test-zarinpal-merchant',
            ZIBAL_MERCHANT_ID='test-zibal-merchant'
        )
        self.settings_context.enable()
        
        self.client = Client()
        self.category = Category.objects.create(name='Test', slug='test')
        self.product = Product.objects.create(
            category=self.category,
            title='Test Product',
            slug='test-product',
            price=10000  # 10000 Tomans
        )
        # Create account items for allocation test
        for i in range(2):
            item = AccountItem.objects.create(product=self.product)
            item.set_plain(f'user{i}@example.com', f'pass{i}', f'notes{i}')
            item.save()
    
    def teardown_method(self):
        """Cleanup after each test"""
        self.settings_context.disable()
    
    @patch('apps.shop.payment_providers.requests.post')
    def test_zarinpal_initiate_payment(self, mock_post):
        """Test ZarinPal payment initiation"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'Status': 100,
            'Authority': 'A00000000000000000000000000000000123456'
        }
        mock_post.return_value = mock_response
        
        provider = ZarinPalProvider(merchant_id='test-merchant', callback_url='http://localhost/callback/')
        success, result = provider.initiate_payment(1000000, 1, 'Test Order')
        
        assert success is True
        assert 'reference' in result
        assert 'payment_url' in result
        assert 'A00000000000000000000000000000000123456' in result['payment_url']
    
    @patch('apps.shop.payment_providers.requests.post')
    def test_zarinpal_initiate_payment_failure(self, mock_post):
        """Test ZarinPal payment initiation failure"""
        mock_response = MagicMock()
        mock_response.json.return_value = {'Status': -1}  # Error status
        mock_post.return_value = mock_response
        
        provider = ZarinPalProvider(merchant_id='test-merchant')
        success, result = provider.initiate_payment(1000000, 1, 'Test Order')
        
        assert success is False
        assert 'error' in result
    
    @patch('apps.shop.payment_providers.requests.post')
    def test_zarinpal_verify_payment_success(self, mock_post):
        """Test ZarinPal payment verification success"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'Status': 100,
            'RefID': '123456789',
            'Amount': 1000000
        }
        mock_post.return_value = mock_response
        
        provider = ZarinPalProvider(merchant_id='test-merchant')
        success, result = provider.verify_payment('A00000000000000000000000000000000123456')
        
        assert success is True
        assert 'reference' in result
        assert 'amount' in result
    
    @patch('apps.shop.payment_providers.requests.post')
    def test_zarinpal_verify_payment_failure(self, mock_post):
        """Test ZarinPal payment verification failure"""
        mock_response = MagicMock()
        mock_response.json.return_value = {'Status': -1}  # Error status
        mock_post.return_value = mock_response
        
        provider = ZarinPalProvider(merchant_id='test-merchant')
        success, result = provider.verify_payment('invalid-authority')
        
        assert success is False
        assert 'error' in result
    
    @patch('apps.shop.payment_providers.requests.post')
    def test_zibal_initiate_payment(self, mock_post):
        """Test Zibal payment initiation"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'result': 0,
            'trackId': '123456789'
        }
        mock_post.return_value = mock_response
        
        provider = ZibalProvider(merchant_id='test-merchant', callback_url='http://localhost/callback/')
        success, result = provider.initiate_payment(1000000, 1, 'Test Order')
        
        assert success is True
        assert 'reference' in result
        assert 'payment_url' in result
        assert '123456789' in result['payment_url']
    
    @patch('apps.shop.payment_providers.requests.post')
    def test_zibal_verify_payment_success(self, mock_post):
        """Test Zibal payment verification success"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'result': 0,
            'amount': 1000000
        }
        mock_post.return_value = mock_response
        
        provider = ZibalProvider(merchant_id='test-merchant')
        success, result = provider.verify_payment('123456789')
        
        assert success is True
        assert result.get('amount') == 1000000
    
    @patch('apps.shop.payment_providers.requests.post')
    def test_checkout_creates_order_and_transaction(self, mock_post):
        """Test checkout creates order and transaction log"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'Status': 100,
            'Authority': 'TEST_AUTHORITY_123'
        }
        mock_post.return_value = mock_response
        
        initial_orders = Order.objects.count()
        response = self.client.post(reverse('shop:checkout'), {
            'product_id': self.product.id,
            'gateway': 'zarinpal'
        }, follow=True)
        
        # Check that an order was created
        assert Order.objects.count() == initial_orders + 1
        order = Order.objects.latest('id')
        assert order.subtotal_amount == self.product.price
        assert order.total == (order.subtotal_amount + order.vat_amount)
        assert order.vat_percent_applied >= 0
        
        # Check transaction log was created
        tx = TransactionLog.objects.filter(order=order).first()
        assert tx is not None
        assert tx.provider == 'zarinpal'

    @patch('apps.shop.views.get_payment_provider')
    def test_checkout_includes_order_id_in_callback_url(self, mock_get_provider):
        """Checkout callback URL must carry order_id for deterministic callback mapping."""
        mock_provider = MagicMock()
        mock_provider.initiate_payment.return_value = (
            True,
            {'reference': 'AUTH-CB-URL', 'payment_url': 'https://gateway.example.test/pay'},
        )
        mock_get_provider.return_value = mock_provider

        response = self.client.post(reverse('shop:checkout'), {
            'product_id': self.product.id,
            'gateway': 'zarinpal',
        })
        assert response.status_code == 302

        order = Order.objects.latest('id')
        callback_url = mock_get_provider.call_args[0][2]
        assert f'/shop/payment/callback/zarinpal/?order_id={order.id}' in callback_url
    
    @patch('apps.shop.payment_providers.requests.post')
    def test_payment_callback_verifies_and_allocates(self, mock_post):
        """Test payment callback verifies payment and allocates inventory"""
        # Create order
        order = Order.objects.create(user=None, total=self.product.price)
        OrderItem.objects.create(order=order, product=self.product, price=self.product.price)
        
        # Create initial transaction log
        tx = TransactionLog.objects.create(
            order=order,
            provider='zarinpal',
            payload={'reference': 'TEST_AUTHORITY'},
            success=False
        )
        
        # Mock verify response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'Status': 100,
            'RefID': '123456789',
            'Amount': int(self.product.price * 100)
        }
        mock_post.return_value = mock_response
        
        # Simulate callback
        response = self.client.get(reverse('shop:payment_callback', args=['zarinpal']), {
            'Status': '100',
            'Authority': 'TEST_AUTHORITY',
            'order_id': order.id
        })
        
        # Refresh order
        order.refresh_from_db()
        
        # Check order marked as paid
        assert order.paid is True
        
        # Check allocation: should have allocated one account item
        order_item = order.items.first()
        assert order_item.account_item is not None
        assert AccountItem.objects.get(id=order_item.account_item.id).allocated is True
    
    @patch('apps.shop.payment_providers.requests.post')
    def test_payment_callback_handles_failure(self, mock_post):
        """Test payment callback handles verification failure"""
        order = Order.objects.create(user=None, total=self.product.price)
        OrderItem.objects.create(order=order, product=self.product, price=self.product.price)
        
        # Mock verify failure response
        mock_response = MagicMock()
        mock_response.json.return_value = {'Status': -1}
        mock_post.return_value = mock_response
        
        response = self.client.get(reverse('shop:payment_callback', args=['zarinpal']), {
            'Status': '-1',
            'Authority': 'INVALID_AUTHORITY'
        })
        
        # Refresh and check order is NOT paid
        order.refresh_from_db()
        assert order.paid is False

    @patch('apps.shop.views.get_payment_provider')
    def test_payment_callback_matches_transaction_by_reference_when_order_id_missing(self, mock_get_provider):
        """When callback lacks order_id, transaction must resolve by reference, not latest provider row."""
        order_target = Order.objects.create(user=None, total=self.product.price, paid=False)
        OrderItem.objects.create(order=order_target, product=self.product, price=self.product.price)
        TransactionLog.objects.create(
            order=order_target,
            provider='zarinpal',
            payload={'reference': 'AUTH-TARGET'},
            success=False,
        )

        order_other = Order.objects.create(user=None, total=self.product.price, paid=False)
        OrderItem.objects.create(order=order_other, product=self.product, price=self.product.price)
        TransactionLog.objects.create(
            order=order_other,
            provider='zarinpal',
            payload={'reference': 'AUTH-OTHER'},
            success=False,
        )

        provider_mock = MagicMock()
        provider_mock.verify_payment.return_value = (
            True,
            {'reference': 'VERIFIED-REF', 'amount': int(order_target.total * 100)},
        )
        mock_get_provider.return_value = provider_mock

        response = self.client.get(
            reverse('shop:payment_callback', args=['zarinpal']),
            {'Status': '100', 'Authority': 'AUTH-TARGET'},
        )
        assert response.status_code == 200

        order_target.refresh_from_db()
        order_other.refresh_from_db()
        assert order_target.paid is True
        assert order_other.paid is False

    @patch('apps.shop.views.get_payment_provider')
    def test_payment_callback_wrong_reference_does_not_mark_order_paid_and_logs_mismatch(self, mock_get_provider, caplog):
        """Wrong callback reference must not mark order as paid and must emit a mismatch log."""
        order = Order.objects.create(user=None, total=self.product.price, paid=False)
        OrderItem.objects.create(order=order, product=self.product, price=self.product.price)
        tx = TransactionLog.objects.create(
            order=order,
            provider='zarinpal',
            payload={'reference': 'AUTH-RIGHT'},
            success=False,
        )

        provider_mock = MagicMock()
        provider_mock.verify_payment.return_value = (
            True,
            {'reference': 'VERIFIED-REF', 'amount': int(order.total * 100)},
        )
        mock_get_provider.return_value = provider_mock
        caplog.set_level(logging.WARNING, logger='shop.payment')

        response = self.client.get(
            reverse('shop:payment_callback', args=['zarinpal']),
            {'Status': '100', 'Authority': 'AUTH-WRONG', 'order_id': order.id},
        )
        assert response.status_code == 400

        order.refresh_from_db()
        tx.refresh_from_db()
        assert order.paid is False
        assert tx.success is False
        assert tx.payload.get('reference_mismatch', {}).get('expected') == 'AUTH-RIGHT'
        assert tx.payload.get('reference_mismatch', {}).get('received') == 'AUTH-WRONG'
        assert 'Reference mismatch' in caplog.text

    @patch('apps.shop.views.get_payment_provider')
    def test_payment_callback_verified_without_order_mapping_returns_400_and_logs(self, mock_get_provider, caplog):
        """Verified callback without resolvable order must fail gracefully (not 500)."""
        provider_mock = MagicMock()
        provider_mock.verify_payment.return_value = (
            True,
            {'reference': 'VERIFIED-REF', 'amount': int(self.product.price * 100)},
        )
        mock_get_provider.return_value = provider_mock
        caplog.set_level(logging.WARNING, logger='shop.payment')

        response = self.client.get(
            reverse('shop:payment_callback', args=['zarinpal']),
            {'Status': '100', 'Authority': 'AUTH-NO-MAP'},
        )
        assert response.status_code == 400
        assert 'Verified payment without order mapping' in caplog.text

    @patch('apps.shop.views.get_payment_provider')
    def test_payment_callback_amount_mismatch_fails_and_logs(self, mock_get_provider, caplog):
        order = Order.objects.create(user=None, total=self.product.price, paid=False)
        OrderItem.objects.create(order=order, product=self.product, price=self.product.price)
        tx = TransactionLog.objects.create(
            order=order,
            provider='zarinpal',
            payload={'reference': 'AUTH-AMOUNT'},
            success=False,
        )
        provider_mock = MagicMock()
        provider_mock.verify_payment.return_value = (
            True,
            {'reference': 'VERIFIED-REF', 'amount': int(order.total * 100) + 250},
        )
        mock_get_provider.return_value = provider_mock
        caplog.set_level(logging.WARNING, logger='shop.payment')

        response = self.client.get(
            reverse('shop:payment_callback', args=['zarinpal']),
            {'Status': '100', 'Authority': 'AUTH-AMOUNT', 'order_id': order.id},
        )
        assert response.status_code == 400

        order.refresh_from_db()
        tx.refresh_from_db()
        assert order.paid is False
        assert tx.success is False
        assert tx.payload.get('amount_mismatch', {}).get('expected') == int(order.total * 100)
        assert tx.payload.get('amount_mismatch', {}).get('received') == int(order.total * 100) + 250
        assert 'Amount mismatch' in caplog.text

    @patch('apps.shop.views.get_payment_provider')
    def test_payment_callback_is_idempotent_on_duplicate_calls(self, mock_get_provider):
        order = Order.objects.create(user=None, total=self.product.price, paid=False)
        order_item = OrderItem.objects.create(order=order, product=self.product, price=self.product.price)
        TransactionLog.objects.create(
            order=order,
            provider='zarinpal',
            payload={'reference': 'AUTH-IDEMPOTENT'},
            success=False,
        )
        provider_mock = MagicMock()
        provider_mock.verify_payment.return_value = (
            True,
            {'reference': 'VERIFIED-REF', 'amount': int(order.total * 100)},
        )
        mock_get_provider.return_value = provider_mock

        first = self.client.get(
            reverse('shop:payment_callback', args=['zarinpal']),
            {'Status': '100', 'Authority': 'AUTH-IDEMPOTENT', 'order_id': order.id},
        )
        second = self.client.get(
            reverse('shop:payment_callback', args=['zarinpal']),
            {'Status': '100', 'Authority': 'AUTH-IDEMPOTENT', 'order_id': order.id},
        )

        assert first.status_code == 200
        assert second.status_code == 200

        order.refresh_from_db()
        order_item.refresh_from_db()
        assert order.paid is True
        assert order_item.account_item_id is not None
        assert AccountItem.objects.filter(product=self.product, allocated=True).count() == 1
        assert TransactionLog.objects.filter(order=order, provider='zarinpal').count() == 1
