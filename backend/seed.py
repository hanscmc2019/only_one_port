import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User, Group


def env(key, default):
    return os.environ.get(key, default)


# Usuarios sembrados: configurables por .env (los defaults son de desarrollo).
# (grupo, username, email, password, is_staff, is_superuser)
seeds = [
    ('SUPERADMIN',                              # acceso total + admin de Django
     env('SEED_SUPERADMIN_USERNAME', 'superadmin'),
     env('SEED_SUPERADMIN_EMAIL', 'super@test.com'),
     env('SEED_SUPERADMIN_PASSWORD', 'admin123'),
     True, True),
    ('ADMIN',                                   # mantenimiento, NO admin de Django
     env('SEED_ADMIN_USERNAME', 'admin'),
     env('SEED_ADMIN_EMAIL', 'admin@test.com'),
     env('SEED_ADMIN_PASSWORD', 'admin123'),
     False, False),
    ('CUSTOMER',                                # solo compras (cuenta demo)
     env('SEED_CUSTOMER_USERNAME', 'cliente'),
     env('SEED_CUSTOMER_EMAIL', 'cliente@test.com'),
     env('SEED_CUSTOMER_PASSWORD', 'cliente123'),
     False, False),
]

for group_name, username, email, password, is_staff, is_superuser in seeds:
    group, _ = Group.objects.get_or_create(name=group_name)
    user, created = User.objects.get_or_create(
        username=username,
        defaults={'email': email, 'is_staff': is_staff, 'is_superuser': is_superuser},
    )
    # Los flags de permisos se reafirman SIEMPRE (seguridad: que el ADMIN
    # "normal" no quede como staff/superuser por pruebas previas).
    user.is_staff = is_staff
    user.is_superuser = is_superuser
    # La contraseña solo se fija al CREAR el usuario, para no pisar un cambio
    # hecho luego desde el admin de Django o con manage.py changepassword.
    if created:
        user.set_password(password)
    user.save()
    user.groups.add(group)

print("Seed de 3 roles completado con exito.")
