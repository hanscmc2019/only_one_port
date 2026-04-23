from rest_framework import serializers
from .models import Category, Product, Cart, CartItem

class CartItemSerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source='product.product_name')
    price = serializers.ReadOnlyField(source='product.price')
    image = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'product_name', 'price', 'image', 'quantity', 'subtotal']
        
    def get_image(self, obj):
        if obj.product.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.product.image.url)
            return obj.product.image.url
        return None

    def get_subtotal(self, obj):
        return (obj.quantity or 0) * (obj.product.price or 0)

class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ['id', 'user', 'is_active', 'created_at', 'items', 'total']

    def get_total(self, obj):
        return sum((item.quantity or 0) * (item.product.price or 0) for item in obj.items.all())
class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = '__all__'

from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        
        user = self.user
        data['username'] = user.username
        data['email'] = user.email
        data['roles'] = list(user.groups.values_list('name', flat=True))
        
        return data
