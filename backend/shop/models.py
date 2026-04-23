from django.db import models

class Category(models.Model):
    category_name = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'category'

def product_image_path(instance, filename):
    ext = filename.split('.')[-1]
    safe_name = "".join([c for c in str(instance.product_name) if c.isalpha() or c.isdigit() or c==' ']).rstrip()
    safe_name = safe_name.replace(' ', '_').lower()
    return f'productos/{safe_name}.{ext}'

class Product(models.Model):
    product_name = models.CharField(max_length=255, blank=True, null=True)
    details = models.TextField(blank=True, null=True)
    price = models.BigIntegerField(blank=True, null=True)
    image = models.ImageField(upload_to=product_image_path, blank=True, null=True, max_length=255)
    id_category = models.ForeignKey(Category, models.DO_NOTHING, db_column='id_category', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'product'

from django.conf import settings

class Cart(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='carts', null=True, blank=True)
    guest_id = models.CharField(max_length=100, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = 'cart'

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = 'cart_item'
        unique_together = ('cart', 'product')
