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
    price_retail = models.BigIntegerField(blank=True, null=True)      # por menor / normal (principal)
    price_wholesale = models.BigIntegerField(blank=True, null=True)   # por mayor / con descuento (opcional)
    stock = models.IntegerField(default=0)  # stock simple; se ignora si el producto tiene variantes
    cost = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)  # costo unitario actual (valorización)
    image = models.ImageField(upload_to=product_image_path, blank=True, null=True, max_length=255)
    id_category = models.ForeignKey(Category, models.DO_NOTHING, db_column='id_category', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'product'

class ProductVariant(models.Model):
    # Variante talla/color con stock propio (solo cliente de ropa). Sin precio: hereda de product.
    id_product = models.ForeignKey(Product, models.DO_NOTHING, db_column='id_product', related_name='variants', blank=True, null=True)
    size = models.CharField(max_length=50, blank=True, null=True)
    color = models.CharField(max_length=50, blank=True, null=True)
    stock = models.IntegerField(default=0)
    sku = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'product_variant'

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
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = 'cart_item'
        unique_together = ('cart', 'product', 'variant')

class Inventory(models.Model):
    # Kardex: un registro por movimiento. El stock actual lo mantiene un trigger
    # de Postgres desde aquí (ver postgres/init/04_inventory.sql).
    INGRESO, AJUSTE, MERMA, DEVOLUCION, VENTA = 'INGRESO', 'AJUSTE', 'MERMA', 'DEVOLUCION', 'VENTA'
    id_product = models.ForeignKey(Product, models.DO_NOTHING, db_column='id_product', related_name='movements')
    id_variant = models.ForeignKey(ProductVariant, models.DO_NOTHING, db_column='id_variant', blank=True, null=True)
    movement_type = models.CharField(max_length=20)  # INGRESO, AJUSTE, MERMA, DEVOLUCION, VENTA
    quantity = models.IntegerField()                 # delta con signo (+entra, -sale)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'Inventory'
