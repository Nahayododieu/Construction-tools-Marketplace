from django.db import models, transaction
from django.conf import settings
from django.contrib.auth import get_user_model

# -------------------------
# CATEGORY MODEL
# -------------------------
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Categories"
    
    def __str__(self):
        return self.name

# -------------------------
# PRODUCT MODEL
# -------------------------
class Product(models.Model):
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('sold', 'Sold'),
        ('expired', 'Expired'),
        ('pending', 'Pending Approval'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ads"
    )
    image = models.ImageField(
        upload_to='advertisements/', 
        default='defaults/no-image.png', 
        blank=True, 
        null=True
    )
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    price = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        related_name='products'
    )
    city = models.CharField(max_length=100)
    stock_quantity = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    views = models.PositiveIntegerField(default=0)
    is_featured = models.BooleanField(default=False)

    # -------------------------
    # SOCIAL FEATURES
    # -------------------------
    likes = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='liked_ads',
        blank=True,
        through='ProductLike'
    )
    shares_count = models.PositiveIntegerField(default=0)  # optional: simple share counter

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        db_table = 'myapp_advertisement'
        verbose_name = 'Product'
        verbose_name_plural = 'Products'

    def __str__(self):
        return self.title

    def total_likes(self):
        return self.likes.count()

    def save(self, *args, **kwargs):
        if self.stock_quantity == 0 and self.status == 'active':
            self.status = 'sold'
        elif self.stock_quantity > 0 and self.status == 'sold':
            self.status = 'active'
        super().save(*args, **kwargs)

    @property
    def is_in_stock(self):
        return self.stock_quantity > 0

    def reduce_stock(self, quantity):
        if quantity < 1:
            raise ValueError("Quantity must be at least 1.")

        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=self.pk)
            if product.stock_quantity < quantity:
                raise ValueError("Not enough products available in stock.")

            product.stock_quantity -= quantity
            if product.stock_quantity == 0 and product.status == 'active':
                product.status = 'sold'
            elif product.stock_quantity > 0 and product.status == 'sold':
                product.status = 'active'

            product.save(update_fields=['stock_quantity', 'status', 'updated_at'])

        self.refresh_from_db(fields=['stock_quantity', 'status', 'updated_at'])

    def restore_stock(self, quantity):
        if quantity < 1:
            raise ValueError("Quantity must be at least 1.")

        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=self.pk)
            product.stock_quantity += quantity
            if product.stock_quantity > 0 and product.status == 'sold':
                product.status = 'active'
            product.save(update_fields=['stock_quantity', 'status', 'updated_at'])

        self.refresh_from_db(fields=['stock_quantity', 'status', 'updated_at'])

# -------------------------
# COMMENT MODEL
# -------------------------
class Comment(models.Model):
    ad = models.ForeignKey(
        Product,
        on_delete=models.CASCADE, 
        related_name='comments'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies'
    )
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']  # Changed to chronological for threaded display

    def __str__(self):
        if self.parent:
            return f"Reply by {self.user.username} to comment on {self.ad.title}"
        return f"Comment by {self.user.username} on {self.ad.title}"

    def get_replies(self):
        """Get all direct replies to this comment"""
        return self.replies.all()

    def is_reply(self):
        """Check if this is a reply to another comment"""
        return self.parent is not None

    def get_thread_depth(self):
        """Get the depth of this comment in the thread"""
        depth = 0
        current = self
        while current.parent:
            depth += 1
            current = current.parent
        return depth

# -------------------------  
# CART MODEL
# -------------------------
class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cart'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart for {self.user.username}"

    def get_total_price(self):
        return sum(item.get_total_price() for item in self.items.all())

    def get_total_items(self):
        return sum(item.quantity for item in self.items.all())


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name='items'
    )
    advertisement = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['cart', 'advertisement']

    def __str__(self):
        return f"{self.quantity} x {self.advertisement.title}"

    def get_total_price(self):
        return self.advertisement.price * self.quantity

# -------------------------  
# MESSAGE MODEL
# -------------------------


class Message(models.Model):
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_messages'
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_messages'
    )
    ad = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='messages'
    )
    subject = models.CharField(max_length=200)
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Message from {self.sender.username} to {self.receiver.username}: {self.subject}"

# -------------------------
# REPORT MODEL
# -------------------------
class Report(models.Model):
    REPORT_TYPES = [
        ('spam', 'Spam'),
        ('inappropriate', 'Inappropriate Content'),
        ('fraud', 'Fraudulent'),
        ('copyright', 'Copyright Violation'),
        ('harassment', 'Harassment'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('investigating', 'Under Investigation'),
        ('resolved', 'Resolved'),
        ('dismissed', 'Dismissed'),
    ]

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reports_made'
    )
    advertisement = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='reports'
    )
    report_type = models.CharField(
        max_length=20,
        choices=REPORT_TYPES,
        default='other'
    )
    description = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    admin_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ['reporter', 'advertisement']  # Prevent duplicate reports

    def __str__(self):
        return f"Report by {self.reporter.username} on '{self.advertisement.title}'"

# -------------------------
# SHARE MODEL
# -------------------------
class Share(models.Model):
    SHARE_METHODS = [
        ('facebook', 'Facebook'),
        ('twitter', 'Twitter'),
        ('whatsapp', 'WhatsApp'),
        ('telegram', 'Telegram'),
        ('email', 'Email'),
        ('link', 'Direct Link'),
        ('other', 'Other'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='shares_made'
    )
    advertisement = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='shares'
    )
    share_method = models.CharField(
        max_length=20,
        choices=SHARE_METHODS,
        default='link'
    )
    shared_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-shared_at']
        unique_together = ['user', 'advertisement', 'share_method']  # Prevent duplicate shares of same method

    def __str__(self):
        return f"{self.user.username} shared '{self.advertisement.title}' via {self.get_share_method_display()}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            Product.objects.filter(pk=self.advertisement_id).update(
                shares_count=models.F('shares_count') + 1
            )


# -------------------------
# ORDER MODEL
# -------------------------
class Order(models.Model):
    ORDER_STATUS = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='orders'
    )
    advertisement = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='orders'
    )
    quantity = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default='pending')
    cancellation_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order #{self.id} by {self.user.username} for {self.advertisement.title}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)


Advertisement = Product


class ProductLike(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        db_column='advertisement_id'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column='user_id'
    )

    class Meta:
        db_table = 'myapp_advertisement_likes'
        unique_together = [('product', 'user')]
        managed = False
