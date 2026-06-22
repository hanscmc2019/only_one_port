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

from .models import Inventory, ProductVariant
from .serializers import InventorySerializer, ProductVariantSerializer

class InventoryViewSet(viewsets.ModelViewSet):
    """Kardex: movimientos de inventario. Crear un movimiento ajusta el stock vía
    trigger de Postgres. List con filtros para alimentar la tabla de inventario."""
    queryset = Inventory.objects.all()
    serializer_class = InventorySerializer
    permission_classes = [IsAdminRole]

    def get_queryset(self):
        qs = Inventory.objects.all().order_by('-created_at', '-id')
        q = self.request.query_params
        if (q.get('id_product') or '').isdigit():
            qs = qs.filter(id_product=q['id_product'])
        if (q.get('id_variant') or '').isdigit():
            qs = qs.filter(id_variant=q['id_variant'])
        if (q.get('id_category') or '').isdigit():
            qs = qs.filter(id_product__id_category=q['id_category'])
        if q.get('movement_type'):
            qs = qs.filter(movement_type=q['movement_type'])
        if q.get('date_from'):
            qs = qs.filter(created_at__date__gte=q['date_from'])
        if q.get('date_to'):
            qs = qs.filter(created_at__date__lte=q['date_to'])
        return qs

class ProductVariantViewSet(viewsets.ModelViewSet):
    queryset = ProductVariant.objects.all().order_by('id')
    serializer_class = ProductVariantSerializer
    permission_classes = [IsAdminRoleOrReadOnly]

    def get_queryset(self):
        qs = ProductVariant.objects.all().order_by('id')
        prod = self.request.query_params.get('id_product')
        if prod and str(prod).isdigit():
            qs = qs.filter(id_product=prod)
        return qs

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

class ConfigView(APIView):
    """Config pública para el frontend estático (que no lee el .env directamente).
    Expone el tipo de negocio para mostrar/ocultar variantes y rotular el 2º precio."""
    permission_classes = [AllowAny]

    def get(self, request):
        from django.conf import settings
        st = settings.STORE_TYPE
        return Response({
            'store_type': st,
            'show_variants': st == 'variants',
            'price_wholesale_label': 'Precio x mayor' if st == 'variants' else 'Precio con descuento',
        })

def _stock_rows(category_id=None):
    """Stock actual por ítem (producto, o por variante si las tiene) + costo y valor.
    Fuente única para la valorización y el export de stock."""
    products = Product.objects.all().select_related('id_category').prefetch_related('variants')
    if category_id and str(category_id).isdigit():
        products = products.filter(id_category=category_id)
    rows, total_units, total_value = [], 0, 0.0
    for p in products:
        cost = float(p.cost) if p.cost is not None else 0.0
        variants = list(p.variants.all())
        targets = variants if variants else [None]
        for v in targets:
            stock = (v.stock if v else p.stock) or 0
            value = stock * cost
            total_units += stock
            total_value += value
            rows.append({
                'id_product': p.id,
                'id_variant': v.id if v else None,
                'id_category': p.id_category_id,
                'category_name': (p.id_category.category_name if p.id_category_id else None),
                'product_name': p.product_name,
                'sku': (v.sku if v and v.sku else f'PROD-{p.id}'),
                'size': v.size if v else None,
                'color': v.color if v else None,
                'stock': stock, 'cost': cost, 'value': round(value, 2),
            })
    return rows, {'units': total_units, 'value': round(total_value, 2), 'count': len(rows)}

class InventoryStockView(APIView):
    """Stock actual por ítem + totales de valorización (S/). Admin."""
    permission_classes = [IsAdminRole]

    def get(self, request):
        rows, totals = _stock_rows(request.query_params.get('id_category'))
        return Response({'items': rows, 'totals': totals})

class InventoryExportView(APIView):
    """Exporta a CSV el stock actual (?kind=stock) o el kardex (?kind=kardex). Admin."""
    permission_classes = [IsAdminRole]

    def get(self, request):
        import csv
        from django.http import HttpResponse
        kind = request.query_params.get('kind', 'stock')
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = f'attachment; filename="inventario_{kind}.csv"'
        w = csv.writer(resp)
        if kind == 'kardex':
            w.writerow(['fecha', 'producto', 'talla', 'color', 'accion', 'cantidad', 'nota'])
            for m in Inventory.objects.all().order_by('-created_at', '-id').select_related('id_product', 'id_variant'):
                w.writerow([
                    m.created_at.strftime('%Y-%m-%d %H:%M'), m.id_product.product_name,
                    (m.id_variant.size if m.id_variant_id else ''), (m.id_variant.color if m.id_variant_id else ''),
                    m.movement_type, m.quantity, m.note or '',
                ])
        else:
            w.writerow(['producto', 'sku', 'talla', 'color', 'stock'])
            rows, _ = _stock_rows()
            for r in rows:
                w.writerow([r['product_name'], r['sku'], r['size'] or '', r['color'] or '', r['stock']])
        return resp

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
        existing = CartItem.objects.filter(cart=user_cart, product=item.product, variant=item.variant).first()
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

        # Variante opcional (talla/color). Debe pertenecer al producto.
        variant = None
        variant_id = parse_int(request.data.get('variant_id'))
        if variant_id is not None:
            try:
                variant = ProductVariant.objects.get(id=variant_id, id_product=product)
            except ProductVariant.DoesNotExist:
                return Response({'error': 'Variante no válida para este producto'}, status=status.HTTP_400_BAD_REQUEST)

        cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product, variant=variant)
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
            unit_price = item.product.price_retail or 0
            subtotal = (item.quantity or 0) * unit_price
            total += subtotal
            variante = ""
            if item.variant_id:
                partes = [p for p in [item.variant.size, item.variant.color] if p]
                if partes:
                    variante = f" [{' / '.join(partes)}]"
            mensaje += f"- {item.quantity}x {item.product.product_name}{variante} (S/ {unit_price})\n"
            
        mensaje += f"\n*Total estimado: S/ {total}*"
        mensaje += "\n\nQuedo a la espera de su confirmación."
        
        from django.conf import settings
        telefono = settings.WHATSAPP_PHONE
        texto_codificado = urllib.parse.quote(mensaje)
        whatsapp_url = f"https://wa.me/{telefono}?text={texto_codificado}"
        
        return Response({"whatsapp_url": whatsapp_url})
