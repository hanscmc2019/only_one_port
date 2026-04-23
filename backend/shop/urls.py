from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoryViewSet, ProductViewSet, CartView, CartItemAddView, CartItemUpdateView, CartItemRemoveView, CheckoutWhatsAppView

router = DefaultRouter()
router.register(r'categories', CategoryViewSet)
router.register(r'products', ProductViewSet)

urlpatterns = [
    path('cart/', CartView.as_view(), name='cart'),
    path('cart/add/', CartItemAddView.as_view(), name='cart-add'),
    path('cart/update/<int:item_id>/', CartItemUpdateView.as_view(), name='cart-update'),
    path('cart/remove/<int:item_id>/', CartItemRemoveView.as_view(), name='cart-remove'),
    path('checkout/whatsapp/', CheckoutWhatsAppView.as_view(), name='checkout-whatsapp'),
    path('', include(router.urls)),
]
