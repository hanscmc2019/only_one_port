from rest_framework import serializers
from .models import Category, Product, ProductVariant, Cart, CartItem, Inventory

class CartItemSerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source='product.product_name')
    price = serializers.ReadOnlyField(source='product.price_retail')  # precio unitario efectivo
    size = serializers.SerializerMethodField()
    color = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'variant', 'product_name', 'price', 'size', 'color', 'image', 'quantity', 'subtotal']

    def get_size(self, obj):
        return obj.variant.size if obj.variant_id else None

    def get_color(self, obj):
        return obj.variant.color if obj.variant_id else None

    def get_image(self, obj):
        if obj.product.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.product.image.url)
            return obj.product.image.url
        return None

    def get_subtotal(self, obj):
        return (obj.quantity or 0) * (obj.product.price_retail or 0)

class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ['id', 'user', 'is_active', 'created_at', 'items', 'total']

    def get_total(self, obj):
        return sum((item.quantity or 0) * (item.product.price_retail or 0) for item in obj.items.all())
class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'

class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = ['id', 'id_product', 'size', 'color', 'stock', 'sku']
        # El stock NO se edita aquí: solo cambia vía movimientos de inventario (kardex).
        read_only_fields = ['stock']

class ProductSerializer(serializers.ModelSerializer):
    variants = ProductVariantSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = '__all__'
        # stock y cost los mantiene el inventario (movimientos/trigger), no la edición de producto.
        read_only_fields = ['stock', 'cost']

    def validate_price_retail(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('El precio no puede ser negativo.')
        return value

    def validate_price_wholesale(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('El precio no puede ser negativo.')
        return value

class InventorySerializer(serializers.ModelSerializer):
    # Campos de solo lectura para mostrar el kardex sin joins en el frontend.
    product_name = serializers.ReadOnlyField(source='id_product.product_name')
    size = serializers.SerializerMethodField()
    color = serializers.SerializerMethodField()

    class Meta:
        model = Inventory
        fields = ['id', 'id_product', 'id_variant', 'product_name', 'size', 'color',
                  'movement_type', 'quantity', 'unit_cost', 'note', 'created_at']

    def get_size(self, obj):
        return obj.id_variant.size if obj.id_variant_id else None

    def get_color(self, obj):
        return obj.id_variant.color if obj.id_variant_id else None

    def validate(self, attrs):
        if attrs.get('quantity') in (None, 0):
            raise serializers.ValidationError('La cantidad del movimiento no puede ser 0.')
        return attrs

from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        
        user = self.user
        data['username'] = user.username
        data['email'] = user.email
        data['roles'] = list(user.groups.values_list('name', flat=True))
        
        return data
