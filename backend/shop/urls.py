from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoryViewSet, ProductViewSet, CartView, CartItemAddView,
    CartItemUpdateView, CartItemRemoveView, CheckoutWhatsAppView,
    InventoryViewSet, ProductVariantViewSet, ConfigView,
    InventoryStockView, InventoryExportView,
)
from .bot_views import (
    ClientsView, OrdersView, ChatView, ApprovePaymentView,
    RejectPaymentView, ResolveClaimView, PaymentProofIngestView,
    SendMessageView, ManualSaleView, RecentSalesView,
)

router = DefaultRouter()
router.register(r'categories', CategoryViewSet)
router.register(r'products', ProductViewSet)
router.register(r'inventory', InventoryViewSet)
router.register(r'variants', ProductVariantViewSet)

urlpatterns = [
    path('config/', ConfigView.as_view(), name='config'),
    # Inventario (admin): deben ir ANTES del router para no chocar con inventory/<pk>/
    path('inventory/stock/', InventoryStockView.as_view(), name='inventory-stock'),
    path('inventory/export/', InventoryExportView.as_view(), name='inventory-export'),
    path('cart/', CartView.as_view(), name='cart'),
    path('cart/add/', CartItemAddView.as_view(), name='cart-add'),
    path('cart/update/<int:item_id>/', CartItemUpdateView.as_view(), name='cart-update'),
    path('cart/remove/<int:item_id>/', CartItemRemoveView.as_view(), name='cart-remove'),
    path('checkout/whatsapp/', CheckoutWhatsAppView.as_view(), name='checkout-whatsapp'),

    # Venta manual del admin (página Ventas)
    path('sales/', ManualSaleView.as_view(), name='sales'),
    path('sales/recent/', RecentSalesView.as_view(), name='sales-recent'),

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
