import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User, Group

super_grp, _ = Group.objects.get_or_create(name='SUPERADMIN')
admin_grp, _ = Group.objects.get_or_create(name='ADMIN')
cust_grp, _ = Group.objects.get_or_create(name='CUSTOMER')

# 1. Superadministrador (Acceso total + Django Admin)
superadmin, _ = User.objects.get_or_create(username='superadmin', defaults={'email':'super@test.com', 'is_staff': True, 'is_superuser': True})
superadmin.set_password('admin123')
superadmin.save()
superadmin.groups.add(super_grp)

# 2. Administrador (Acceso a Mantenimiento de Productos, pero NO al Django Admin)
# Le quitamos is_staff e is_superuser al admin "normal" en caso los tuviera de pruebas previas
admin, _ = User.objects.get_or_create(username='admin', defaults={'email':'admin@test.com', 'is_staff': False, 'is_superuser': False})
admin.is_staff = False
admin.is_superuser = False
admin.set_password('admin123')
admin.save()
admin.groups.add(admin_grp)

# 3. Cliente (Solo compras)
cust, _ = User.objects.get_or_create(username='cliente', defaults={'email':'cliente@test.com', 'is_staff': False, 'is_superuser': False})
cust.set_password('cliente123')
cust.save()
cust.groups.add(cust_grp)

print("Seed de 3 roles completado con exito.")
