from rest_framework import viewsets
from rest_framework.permissions import BasePermission
from .models import Category, Product
from .serializers import CategorySerializer, ProductSerializer

def _is_admin(user):
    return bool(user and user.is_authenticated and (
        user.is_superuser or user.groups.filter(name__in=['ADMIN', 'SUPERADMIN']).exists()
    ))

class IsAdminRoleOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        return _is_admin(request.user)

class IsAdminRole(BasePermission):
    # Admin para TODOS los métodos (lectura incluida): ventas/inventario no son públicos.
    def has_permission(self, request, view):
        return _is_admin(request.user)

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminRoleOrReadOnly]

    def destroy(self, request, *args, **kwargs):
        from rest_framework.response import Response
        from rest_framework import status
        instance = self.get_object()
        if Product.objects.filter(id_category=instance).exists():
            return Response(
                {'error': 'No se puede eliminar la categoría: tiene productos asociados.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().destroy(request, *args, **kwargs)

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsAdminRoleOrReadOnly]

    def get_queryset(self):
        qs = Product.objects.all()
        # Filtro por categoría: ?id_category=<id>
        cat = self.request.query_params.get('id_category')
        if cat and str(cat).isdigit():
            qs = qs.filter(id_category=cat)
        # Búsqueda por nombre: ?search=<texto>
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(product_name__icontains=search)
        return qs.order_by('id')

from .models import Sale, Inventory
from .serializers import SaleSerializer, InventorySerializer

class SaleViewSet(viewsets.ModelViewSet):
    queryset = Sale.objects.all().order_by('-id')
    serializer_class = SaleSerializer
    permission_classes = [IsAdminRole]

class InventoryViewSet(viewsets.ModelViewSet):
    queryset = Inventory.objects.all().order_by('-id')
    serializer_class = InventorySerializer
    permission_classes = [IsAdminRole]

from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.throttling import ScopedRateThrottle
from .serializers import CustomTokenObtainPairSerializer

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    # Límite estricto anti fuerza bruta (rate 'login' en settings).
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        # Tras un login exitoso, fusionar el carrito de invitado (si lo hay).
        if response.status_code == 200:
            guest_id = request.headers.get('X-Guest-ID')
            username = request.data.get('username')
            if guest_id and username:
                from django.contrib.auth.models import User
                try:
                    merge_guest_cart(guest_id, User.objects.get(username=username))
                except User.DoesNotExist:
                    pass
        return response

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import Cart, CartItem
from .serializers import CartSerializer
import urllib.parse

def parse_int(value):
    """Convierte a int o devuelve None si no es un entero válido."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def merge_guest_cart(guest_id, user):
    """Fusiona el carrito de invitado (X-Guest-ID) con el del usuario al loguearse."""
    try:
        guest_cart = Cart.objects.get(guest_id=guest_id, user=None, is_active=True)
    except Cart.DoesNotExist:
        return
    user_cart, _ = Cart.objects.get_or_create(user=user, is_active=True)
    if guest_cart.pk == user_cart.pk:
        return
    for item in list(guest_cart.items.all()):
        existing = CartItem.objects.filter(cart=user_cart, product=item.product).first()
        if existing:
            existing.quantity += item.quantity
            existing.save()
            item.delete()
        else:
            item.cart = user_cart
            item.save()
    guest_cart.delete()

def get_cart(request):
    if request.user and request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user, is_active=True)
        return cart
    else:
        guest_id = request.headers.get('X-Guest-ID')
        if not guest_id:
            return None
        cart, _ = Cart.objects.get_or_create(guest_id=guest_id, user=None, is_active=True)
        return cart

class CartView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        cart = get_cart(request)
        if not cart:
            return Response({'error': 'No guest_id provided'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = CartSerializer(cart, context={'request': request})
        return Response(serializer.data)

class CartItemAddView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        cart = get_cart(request)
        if not cart:
            return Response({'error': 'No guest_id provided'}, status=status.HTTP_400_BAD_REQUEST)
            
        product_id = parse_int(request.data.get('product_id'))
        if product_id is None:
            return Response({'error': 'product_id es requerido y debe ser numérico'}, status=status.HTTP_400_BAD_REQUEST)

        quantity = parse_int(request.data.get('quantity', 1))
        if quantity is None or quantity < 1:
            return Response({'error': 'quantity debe ser un entero positivo'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Response({'error': 'Product not found'}, status=status.HTTP_404_NOT_FOUND)

        cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product)
        if not created:
            cart_item.quantity += quantity
        else:
            cart_item.quantity = quantity
        cart_item.save()

        serializer = CartSerializer(cart, context={'request': request})
        return Response(serializer.data)

class CartItemUpdateView(APIView):
    permission_classes = [AllowAny]

    def put(self, request, item_id):
        cart = get_cart(request)
        if not cart:
            return Response({'error': 'No guest_id provided'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            cart_item = CartItem.objects.get(id=item_id, cart=cart)
        except CartItem.DoesNotExist:
            return Response({'error': 'Item not found'}, status=status.HTTP_404_NOT_FOUND)

        quantity = parse_int(request.data.get('quantity', 1))
        if quantity is None:
            return Response({'error': 'quantity debe ser un entero'}, status=status.HTTP_400_BAD_REQUEST)
        if quantity > 0:
            cart_item.quantity = quantity
            cart_item.save()
        else:
            cart_item.delete()

        serializer = CartSerializer(cart, context={'request': request})
        return Response(serializer.data)

class CartItemRemoveView(APIView):
    permission_classes = [AllowAny]

    def delete(self, request, item_id):
        cart = get_cart(request)
        if not cart:
            return Response({'error': 'No guest_id provided'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            cart_item = CartItem.objects.get(id=item_id, cart=cart)
            cart_item.delete()
            serializer = CartSerializer(cart, context={'request': request})
            return Response(serializer.data)
        except CartItem.DoesNotExist:
            return Response({'error': 'Item not found'}, status=status.HTTP_404_NOT_FOUND)

class CheckoutWhatsAppView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        cart = get_cart(request)
        if not cart:
            return Response({'error': 'No guest_id provided'}, status=status.HTTP_400_BAD_REQUEST)

        items = cart.items.all()
        
        if not items:
            return Response({'error': 'El carrito está vacío'}, status=status.HTTP_400_BAD_REQUEST)
            
        mensaje = "Hola, me gustaría solicitar una cotización para los siguientes productos:\n\n"
        total = 0
        
        for item in items:
            subtotal = (item.quantity or 0) * (item.product.price or 0)
            total += subtotal
            mensaje += f"- {item.quantity}x {item.product.product_name} (S/ {item.product.price})\n"
            
        mensaje += f"\n*Total estimado: S/ {total}*"
        mensaje += "\n\nQuedo a la espera de su confirmación."
        
        from django.conf import settings
        telefono = settings.WHATSAPP_PHONE
        texto_codificado = urllib.parse.quote(mensaje)
        whatsapp_url = f"https://wa.me/{telefono}?text={texto_codificado}"
        
        return Response({"whatsapp_url": whatsapp_url})
