from rest_framework import viewsets
from rest_framework.permissions import BasePermission
from .models import Category, Product
from .serializers import CategorySerializer, ProductSerializer

class IsAdminRoleOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.is_superuser or request.user.groups.filter(name__in=['ADMIN', 'SUPERADMIN']).exists()

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminRoleOrReadOnly]

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsAdminRoleOrReadOnly]

from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import CustomTokenObtainPairSerializer

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import Cart, CartItem
from .serializers import CartSerializer
import urllib.parse

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
            
        product_id = request.data.get('product_id')
        quantity = int(request.data.get('quantity', 1))

        if not product_id:
            return Response({'error': 'product_id is required'}, status=status.HTTP_400_BAD_REQUEST)
            
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

        quantity = int(request.data.get('quantity', 1))
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
        
        telefono = "51923949691"
        texto_codificado = urllib.parse.quote(mensaje)
        whatsapp_url = f"https://wa.me/{telefono}?text={texto_codificado}"
        
        return Response({"whatsapp_url": whatsapp_url})
