from django.contrib import admin
from .models import Category, Product, Cart, CartItem, Sale, Inventory

admin.site.register(Category)
admin.site.register(Product)
admin.site.register(Cart)
admin.site.register(CartItem)
admin.site.register(Sale)
admin.site.register(Inventory)
