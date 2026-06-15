from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoryViewSet, ProductViewSet, CartView, CartItemAddView,
    CartItemUpdateView, CartItemRemoveView, CheckoutWhatsAppView,
    SaleViewSet, InventoryViewSet,
)
from .bot_views import (
    ClientsView, OrdersView, ChatView, ApprovePaymentView,
    RejectPaymentView, ResolveClaimView, PaymentProofIngestView,
    SendMessageView,
)

router = DefaultRouter()
router.register(r'categories', CategoryViewSet)
router.register(r'products', ProductViewSet)
router.register(r'sales', SaleViewSet)
router.register(r'inventory', InventoryViewSet)

urlpatterns = [
    path('cart/', CartView.as_view(), name='cart'),
    path('cart/add/', CartItemAddView.as_view(), name='cart-add'),
    path('cart/update/<int:item_id>/', CartItemUpdateView.as_view(), name='cart-update'),
    path('cart/remove/<int:item_id>/', CartItemRemoveView.as_view(), name='cart-remove'),
    path('checkout/whatsapp/', CheckoutWhatsAppView.as_view(), name='checkout-whatsapp'),

    # Monitor de Ventas del bot (admin)
    path('bot/clients/', ClientsView.as_view(), name='bot-clients'),
    path('bot/orders/', OrdersView.as_view(), name='bot-orders'),
    path('bot/chat/', ChatView.as_view(), name='bot-chat'),
    path('bot/chat/send/', SendMessageView.as_view(), name='bot-chat-send'),
    path('bot/orders/<int:order_id>/approve/', ApprovePaymentView.as_view(), name='bot-approve'),
    path('bot/orders/<int:order_id>/reject/', RejectPaymentView.as_view(), name='bot-reject'),
    path('bot/tickets/<int:ticket_id>/resolve/', ResolveClaimView.as_view(), name='bot-resolve'),
    path('bot/payment-proof/', PaymentProofIngestView.as_view(), name='bot-payment-proof'),

    path('', include(router.urls)),
]
