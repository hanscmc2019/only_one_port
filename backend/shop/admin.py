from django.contrib import admin
from .models import Category, Product, ProductVariant, Cart, CartItem, Inventory

admin.site.register(Category)
admin.site.register(Product)
admin.site.register(ProductVariant)
admin.site.register(Cart)
admin.site.register(CartItem)
admin.site.register(Inventory)
