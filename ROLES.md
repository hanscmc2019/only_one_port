# Roles y permisos — EShopper

Documentación de los roles del sistema, cómo se determinan y qué puede hacer cada uno.

## Roles disponibles

Hay 3 roles (más el visitante anónimo). Son **Groups de Django**, sembrados por `backend/entrypoint.sh` en cada arranque:

| Rol | Usuario seed | Contraseña | `is_staff` | `is_superuser` |
|---|---|---|---|---|
| Invitado | — (anónimo) | — | — | — |
| `CUSTOMER` | `cliente` | `cliente123` | ❌ | ❌ |
| `ADMIN` | `admin` | `admin123` | ❌ | ❌ |
| `SUPERADMIN` | `superadmin` | `admin123` | ✅ | ✅ |

> Las contraseñas semilla son de desarrollo. Cambiarlas para producción.

## Cómo se determina el rol

1. `POST /api/login/` → `CustomTokenObtainPairSerializer` devuelve `access`, `refresh`, `username`, `email` y `roles` (lista de groups).
2. `login.html` guarda todo en `localStorage` (`access_token`, `refresh_token`, `user_roles`, `username`).
3. `web/js/load_components.js` lee `user_roles` y ajusta la UI (mostrar/ocultar enlaces, redirigir, auto-logout).
4. `web/js/main.js` adjunta en cada llamada AJAX: `Authorization: Bearer <token>` (si hay) y `X-Guest-ID` (siempre).

**La UI es solo cosmética.** La autorización real se aplica en el backend (`shop/views.py`):

- `IsAdminRoleOrReadOnly` — lectura abierta; escritura de productos/categorías solo para `is_superuser` o grupos `ADMIN`/`SUPERADMIN`.
- `IsAdminRole` — exige admin para **todos** los métodos (ventas/inventario, no públicos).
- El login está limitado a **5 intentos/min por IP** (DRF throttling, scope `login`).

## Capacidades por rol

| Acción | Invitado | CUSTOMER | ADMIN | SUPERADMIN |
|---|:--:|:--:|:--:|:--:|
| Ver catálogo / detalle | ✅ | ✅ | ✅ | ✅ |
| Carrito (agregar/editar/quitar) | ✅ | ✅ | ✅ | ✅ |
| Checkout por WhatsApp | ✅ | ✅ | ✅ | ✅ |
| Fusión de carrito al loguearse | — | ✅ | ✅ | ✅ |
| Mantenimiento de productos/categorías (CRUD) | ❌ | ❌ | ✅ | ✅ |
| Ventas / inventario (`/api/sales/`, `/api/inventory/`) | ❌ | ❌ | ✅ | ✅ |
| Monitor de Ventas del bot (`monitor_ventas.html`, `/api/bot/*`) | ❌ | ❌ | ✅ | ✅ |
| Panel de admin de Django (`/admin/`) | ❌ | ❌ | ❌ | ✅ |

### Invitado (anónimo)
Navega y compra identificándose por la cabecera `X-Guest-ID` (generada y guardada en `localStorage`). Su carrito se fusiona con el del usuario al iniciar sesión (`merge_guest_cart()`).

### CUSTOMER
Igual que el invitado, pero autenticado. Hoy **no aporta capacidades extra** de compra sobre el invitado (pendiente: historial de pedidos).

### ADMIN
Hereda todo lo del cliente y además:
- Ve el enlace **"Mantenimiento"** en el navbar (oculto para no-admins; si un no-admin abre la URL directa, `load_components.js` lo redirige a `index.html`).
- CRUD de productos y categorías en `mantenimiento_productos.html` (`POST/PUT/DELETE` sobre `/api/products/` y `/api/categories/`).
- Gestión manual de ventas e inventario vía `/api/sales/` y `/api/inventory/`.
- **Auto-logout** tras 30 min de inactividad (solo admins).
- **No** tiene acceso al admin de Django (`is_staff=False`).

### SUPERADMIN
Hereda todo lo del ADMIN y además:
- Enlace **"Panel Django"** en el navbar → `/admin/`.
- Acceso total al admin de Django (`is_superuser=True`): usuarios, grupos y todos los modelos registrados.

## Mapa rol → endpoints

| Endpoint | Invitado | CUSTOMER | ADMIN | SUPERADMIN |
|---|:--:|:--:|:--:|:--:|
| `GET /api/products/`, `/api/categories/` | ✅ | ✅ | ✅ | ✅ |
| `POST/PUT/DELETE /api/products/`, `/api/categories/` | ❌ | ❌ | ✅ | ✅ |
| `/api/cart/*`, `/api/checkout/whatsapp/` | ✅ | ✅ | ✅ | ✅ |
| `/api/sales/`, `/api/inventory/` | ❌ | ❌ | ✅ | ✅ |
| `/api/bot/*` (monitor del bot) | ❌ | ❌ | ✅ | ✅ |
| `/admin/` (Django) | ❌ | ❌ | ❌ | ✅ |
