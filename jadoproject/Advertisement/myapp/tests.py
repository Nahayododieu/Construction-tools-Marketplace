from decimal import Decimal

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from .models import Product, Cart, CartItem, Category, Order, Share


class ProjectCompletionTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Cement', slug='cement')
        self.owner = User.objects.create_user(username='owner', password='testpass123')
        self.user = User.objects.create_user(
            username='buyer',
            password='testpass123',
            email='buyer@example.com'
        )
        self.staff = User.objects.create_user(
            username='staff',
            password='testpass123',
            is_staff=True
        )
        self.ad = Product.objects.create(
            user=self.owner,
            title='Premium Cement',
            slug='premium-cement',
            description='High quality cement for construction projects.',
            price=Decimal('150.00'),
            category=self.category,
            city='Johannesburg',
            status='active',
            stock_quantity=10,
        )

    def test_share_creation_updates_share_counter_once(self):
        Share.objects.create(user=self.user, advertisement=self.ad, share_method='link')
        self.ad.refresh_from_db()
        self.assertEqual(self.ad.shares_count, 1)

        Share.objects.get(user=self.user, advertisement=self.ad, share_method='link')
        self.ad.refresh_from_db()
        self.assertEqual(self.ad.shares_count, 1)

    def test_order_creation_does_not_change_share_counter(self):
        Order.objects.create(user=self.user, advertisement=self.ad, quantity=2, status='completed')
        self.ad.refresh_from_db()
        self.assertEqual(self.ad.shares_count, 0)

    def test_advertisement_list_supports_text_search(self):
        response = self.client.get(reverse('advertisement-list'), {'search': 'cement'})
        self.assertContains(response, 'Premium Cement')

    def test_visitors_can_view_product_detail_page(self):
        response = self.client.get(reverse('advertisement-detail', kwargs={'slug': self.ad.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Premium Cement')

    def test_checkout_redirects_to_cart_when_empty(self):
        self.client.login(username='buyer', password='testpass123')
        response = self.client.get(reverse('checkout'))
        self.assertRedirects(response, reverse('cart'))

    def test_checkout_renders_with_cart_items(self):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, advertisement=self.ad, quantity=1)
        self.client.login(username='buyer', password='testpass123')
        response = self.client.get(reverse('checkout'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Premium Cement')

    def test_signup_collects_profile_fields_and_creates_regular_user(self):
        response = self.client.post(reverse('signup'), {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'first_name': 'New',
            'last_name': 'User',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
            'accept_terms': 'on',
        })
        self.assertRedirects(response, reverse('login'))
        new_user = User.objects.get(username='newuser')
        self.assertEqual(new_user.email, 'newuser@example.com')
        self.assertEqual(new_user.first_name, 'New')
        self.assertFalse(new_user.is_staff)

    def test_admin_dashboard_supplies_top_performer_context(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('admin-dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('most_viewed_ads', response.context)
        self.assertIn('most_active_users', response.context)

    def test_user_signups_route_is_available(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('user-signups'))
        self.assertEqual(response.status_code, 200)

    def test_non_staff_cannot_access_product_management(self):
        self.client.login(username='buyer', password='testpass123')
        response = self.client.get(reverse('advertisement-create'))
        self.assertRedirects(response, reverse('advertisement-list'))

    def test_login_accepts_email_address(self):
        response = self.client.post(reverse('login'), {
            'username': 'buyer@example.com',
            'password': 'testpass123',
        })
        self.assertRedirects(response, reverse('user-dashboard'))

    def test_successful_login_clears_rate_limit_counter(self):
        cache.set('login_attempts_127.0.0.1', 4, 300)
        response = self.client.post(reverse('login'), {
            'username': 'buyer',
            'password': 'testpass123',
        })
        self.assertRedirects(response, reverse('user-dashboard'))
        self.assertIsNone(cache.get('login_attempts_127.0.0.1'))

    def test_standard_django_admin_route_is_available(self):
        admin_user = User.objects.create_superuser(
            username='siteadmin',
            email='siteadmin@example.com',
            password='AdminPass123!'
        )
        self.client.force_login(admin_user)
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Site administration')

    def test_user_profile_does_not_show_create_ad_option(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('user-profile'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Create New Ad')
        self.assertNotContains(response, 'Create your first ad')

    def test_category_page_uses_product_wording(self):
        response = self.client.get(reverse('category-list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Total Products')
        self.assertContains(response, 'View Products (1)')
        self.assertNotContains(response, 'Total Advertisements')
        self.assertNotContains(response, 'View Ads')

    def test_landing_page_shows_view_product_button_and_category_link(self):
        response = self.client.get(reverse('landing'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{reverse("product-list")}"', html=False)
        self.assertContains(response, 'View Products')
        self.assertContains(response, f'{reverse("product-list")}?category={self.category.id}')
        self.assertContains(response, reverse('product-detail', kwargs={'slug': self.ad.slug}))

    def test_authenticated_user_can_add_product_to_cart(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('add-to-cart', kwargs={'slug': self.ad.slug}), {
            'quantity': 2,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CartItem.objects.get(cart__user=self.user).quantity, 2)

    def test_authenticated_user_can_remove_product_from_cart(self):
        cart = Cart.objects.create(user=self.user)
        item = CartItem.objects.create(cart=cart, advertisement=self.ad, quantity=1)
        self.client.force_login(self.user)
        response = self.client.post(reverse('remove-cart-item', kwargs={'item_id': item.id}))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CartItem.objects.filter(id=item.id).exists())

    def test_admin_can_store_available_stock_on_product(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse('advertisement-create'), {
            'title': 'Roofing Sheets',
            'slug': 'roofing-sheets',
            'description': 'Durable roofing sheets for commercial sites.',
            'price': '220.00',
            'category': self.category.id,
            'city': 'Durban',
            'stock_quantity': 25,
            'is_featured': '',
            'status': 'active',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Product.objects.get(slug='roofing-sheets').stock_quantity, 25)

    def test_buy_now_reduces_available_stock(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('advertisement-buy', kwargs={'slug': self.ad.slug}), {
            'buyer_name': 'Buyer User',
            'buyer_email': 'buyer@example.com',
            'payment_method': 'cod',
            'quantity': 3,
            'notes': '',
        })
        self.assertEqual(response.status_code, 200)
        self.ad.refresh_from_db()
        self.assertEqual(self.ad.stock_quantity, 7)

    def test_cannot_add_more_items_to_cart_than_stock(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('add-to-cart', kwargs={'slug': self.ad.slug}), {
            'quantity': 11,
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(CartItem.objects.filter(cart__user=self.user).exists())

    def test_checkout_reduces_stock_for_purchased_items(self):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, advertisement=self.ad, quantity=4)
        self.client.force_login(self.user)
        response = self.client.post(reverse('process-checkout'), {
            'buyer_name': 'Buyer User',
            'buyer_email': 'buyer@example.com',
            'payment_method': 'cod',
            'shipping_address': '123 Main Street',
            'notes': '',
        })
        self.assertEqual(response.status_code, 200)
        self.ad.refresh_from_db()
        self.assertEqual(self.ad.stock_quantity, 6)

    def test_checkout_success_shows_purchased_item_totals_after_cart_is_cleared(self):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, advertisement=self.ad, quantity=4)
        self.client.force_login(self.user)
        response = self.client.post(reverse('process-checkout'), {
            'buyer_name': 'Buyer User',
            'buyer_email': 'buyer@example.com',
            'payment_method': 'cod',
            'shipping_address': '123 Main Street',
            'notes': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<p><strong>Total Items Purchased:</strong> 4</p>',
            html=True,
        )
        self.assertContains(
            response,
            '<p><strong>Total Amount:</strong> $600.00</p>',
            html=True,
        )
        self.assertFalse(CartItem.objects.filter(cart=cart).exists())

    def test_customer_can_cancel_order_with_optional_reason(self):
        order = Order.objects.create(user=self.user, advertisement=self.ad, quantity=1, status='pending')
        self.client.force_login(self.user)
        response = self.client.post(reverse('cancel-order', kwargs={'pk': order.pk}), {
            'cancellation_reason': 'Found a supplier closer to the site.',
        })
        self.assertRedirects(response, reverse('user-dashboard'))
        order.refresh_from_db()
        self.assertEqual(order.status, 'cancelled')
        self.assertEqual(order.cancellation_reason, 'Found a supplier closer to the site.')

    def test_customer_can_cancel_order_without_reason(self):
        order = Order.objects.create(user=self.user, advertisement=self.ad, quantity=1, status='pending')
        self.client.force_login(self.user)
        response = self.client.post(reverse('cancel-order', kwargs={'pk': order.pk}), {
            'cancellation_reason': '',
        })
        self.assertRedirects(response, reverse('user-dashboard'))
        order.refresh_from_db()
        self.assertEqual(order.status, 'cancelled')
        self.assertEqual(order.cancellation_reason, '')
