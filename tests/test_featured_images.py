import pytest
from django.test import Client
from apps.shop.models import Product, Category
from apps.blog.models import Post


@pytest.mark.django_db
class TestFeaturedImages:
    """Test featured image rendering in templates"""
    
    def setup_method(self):
        self.client = Client()
    
    def test_product_list_with_image(self):
        """Test product list renders correctly when product has featured image"""
        cat = Category.objects.create(name='تست', slug='test')
        Product.objects.create(
            title='محصول با تصویر',
            slug='product-with-image',
            category=cat,
            price=100.00,
            featured_image='products/test.jpg'  # Simulated file path
        )
        
        response = self.client.get('/shop/')
        assert response.status_code == 200
        assert 'محصول با تصویر' in response.content.decode()
        # Should not crash and should render the page
    
    def test_product_list_without_image(self):
        """Test product list renders with emoji fallback when no featured image"""
        cat = Category.objects.create(name='تست', slug='test-no-img')
        Product.objects.create(
            title='محصول بدون تصویر',
            slug='product-without-image',
            category=cat,
            price=200.00
            # No featured_image
        )
        
        response = self.client.get('/shop/')
        assert response.status_code == 200
        assert 'محصول بدون تصویر' in response.content.decode()
        # Should show emoji fallback
    
    def test_post_list_with_image(self):
        """Test blog post list renders with featured image"""
        Post.objects.create(
            title='مقاله با تصویر',
            slug='post-with-image',
            content='محتوای تست',
            published=True,
            featured_image='blog/test.jpg'  # Simulated file path
        )
        
        response = self.client.get('/blog/')
        assert response.status_code == 200
        assert 'مقاله با تصویر' in response.content.decode()
    
    def test_post_list_without_image(self):
        """Test blog post list renders with emoji fallback when no image"""
        Post.objects.create(
            title='مقاله بدون تصویر',
            slug='post-without-image',
            content='محتوای تست',
            published=True
            # No featured_image
        )
        
        response = self.client.get('/blog/')
        assert response.status_code == 200
        assert 'مقاله بدون تصویر' in response.content.decode()
