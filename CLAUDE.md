# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Resumen

Tienda de e-commerce dockerizada para una tienda peruana. Tres servicios en ejecución (ver `docker-compose.yml`): **nginx** sirve el frontend estático y hace de reverse proxy hacia la API, **postgres** guarda los datos, y **backend** es una API REST de Django. El checkout se hace generando un enlace de WhatsApp (`wa.me`) en lugar de un flujo de pago real. Los textos de la UI y muchos comentarios están en español.

## Ejecución

Todo el stack corre mediante Docker Compose; no hay un entorno de desarrollo de Python/Node a nivel del host.

```bash
# crear el .env en la raíz la primera vez (ver "Configuración" abajo para las variables)
docker compose up --build        # levanta todo; sitio en http://localhost:8090
docker compose down              # detiene
docker compose logs -f backend   # ver logs del backend
```

- Solo nginx está publicado (`8090:80`). `postgres` y `backend` solo son accesibles dentro de la red `app-network`; el frontend siempre habla con la API a través de nginx por rutas relativas `/api/`, nunca con un host/puerto fijo.
- El contenedor del backend monta `./backend` y `./media` como volúmenes, así que los cambios en Python los recoge el autoreload de Django sin reconstruir. Solo reconstruir cuando cambian `requirements.txt` o el Dockerfile.
- `backend/entrypoint.sh` ejecuta `migrate`, `collectstatic` (estáticos del admin vía WhiteNoise) y vuelve a sembrar usuarios/grupos en cada arranque del contenedor (es idempotente).

### Configuración (`.env`)

La config sensible vive en `.env` (en la raíz, **ignorado por git**). El servicio `backend` la inyecta vía `env_file` y `settings.py` la lee con `os.environ`. Variables: `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `POSTGRES_*`, `WHATSAPP_PHONE`.

- **Gotcha:** los `$` en valores del `.env` deben escaparse como `$$` (docker-compose interpola `$` en `env_file`).
- Generar una `SECRET_KEY` nueva y pegarla en la variable `SECRET_KEY` del `.env`:
  ```bash
  docker compose exec backend python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
  ```
- Para producción: `DEBUG=False`, y restringir `ALLOWED_HOSTS`/`CORS_ALLOWED_ORIGINS`/`CSRF_TRUSTED_ORIGINS` al dominio real.

### Comandos de administración del backend

Se ejecutan dentro del contenedor:

```bash
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py makemigrations shop
docker compose exec backend python manage.py createsuperuser
docker compose exec backend python manage.py test            # runner de tests (shop/tests.py está vacío por ahora)
docker compose exec backend python manage.py test shop.tests.SomeTest.test_x   # un solo test
```

## Arquitectura

### División del modelo de datos — leer esto antes de tocar los modelos o la BD

El esquema está definido en **dos lugares** y deben mantenerse sincronizados manualmente:

- `postgres/init/01_schema.sql` crea las tablas `category`, `product`, `Inventory` y `sale`. Solo se ejecuta **cuando el volumen de datos de postgres está vacío** (init del entrypoint de Docker). Para volver a aplicarlo hay que borrar `./postgres_data` y reiniciar.
- En `backend/shop/models.py`, `Category` y `Product` son `managed = False` — mapean sobre las tablas creadas por el SQL y Django **no** generará ni aplicará migraciones para ellas. Cambiar estos modelos no cambia la BD; en su lugar hay que editar `01_schema.sql` (y resetear el volumen).
- `Cart` y `CartItem` son `managed = True` (migraciones normales de Django en `backend/shop/migrations/`). `Sale` e `Inventory` también tienen modelo (`managed = False`, mapean a las tablas `sale` / `Inventory` del SQL init).

### Superficie de la API

`core/urls.py` monta la autenticación en `/api/login/` + `/api/token/refresh/` (SimpleJWT) e incluye `shop/urls.py` bajo `/api/`:

- `categories/`, `products/` — `ModelViewSet`s de DRF. `products/` acepta `?id_category=<id>` y `?search=<texto>`. Todas las listas soportan paginación opcional `?limit=&offset=` (sin esos params devuelven lista plana).
- `cart/`, `cart/add/`, `cart/update/<id>/`, `cart/remove/<id>/` — `APIView`s simples.
- `checkout/whatsapp/` — construye una URL `wa.me` con el contenido del carrito (número desde `settings.WHATSAPP_PHONE` / env).
- `sales/`, `inventory/` — `ModelViewSet`s **solo admin** (registro manual de ventas y movimientos de inventario; aún no se auto-registran en una compra).

### Identidad del carrito (invitado vs. autenticado)

`get_cart()` en `shop/views.py` es la única fuente de verdad. Las peticiones autenticadas obtienen un carrito por `user`; las anónimas se identifican por la cabecera `X-Guest-ID`. El frontend genera y guarda ese id en `localStorage` y lo adjunta a **todas** las llamadas AJAX mediante un `$.ajaxSetup` global con `beforeSend` (ver `web/js/main.js`), junto con la cabecera `Authorization: Bearer` cuando existe un token. Al iniciar sesión, `merge_guest_cart()` fusiona el carrito de invitado (por `X-Guest-ID`) en el del usuario.

### Autorización / roles

Los roles son **Groups** de Django: `SUPERADMIN`, `ADMIN`, `CUSTOMER`, sembrados por `entrypoint.sh` (usuarios por defecto: `superadmin/admin123`, `admin/admin123`, `cliente/cliente123`). En `shop/views.py`: `IsAdminRoleOrReadOnly` deja la lectura abierta y restringe la escritura de productos/categorías a superusuarios o grupos ADMIN/SUPERADMIN; `IsAdminRole` exige admin para **todos** los métodos (ventas/inventario, no públicos). `CustomTokenObtainPairSerializer` agrega `username`, `email` y `roles` a la respuesta del login; el frontend los guarda en `localStorage` y aplica el control de acceso a nivel de UI en `web/js/load_components.js`. El login está limitado a 5/min por IP (DRF throttling, scope `login`).

### Frontend

`web/` es una plantilla estática de Bootstrap 4 + jQuery (sin paso de build para el HTML/JS). El chrome compartido se carga por componentes:

- `web/components/topbar.html` / `navbar.html` / `footer.html` se inyectan en tiempo de ejecución por `web/js/load_components.js` dentro de `#topbar-placeholder` / `#navbar-placeholder` / `#footer-placeholder`, que luego aplica la UI según rol (ocultar el link de mantenimiento de admin, cambiar los botones de login, auto-logout de admin por inactividad).
- El CSS no tiene paso de build: se edita `web/css/style.css` directamente. Los colores/tamaños de marca están tokenizados como variables CSS (`--brand-*`) y se configuran en `web/css/theme.css` (cargado después de `style.css`), que es el único archivo que el programador edita para re-skinnear el sitio.

### Ruteo de nginx (`nginx/default.conf`)

`/` → estático `web/`; `/media/` → imágenes de productos subidas; `/api/`, `/admin/`, `/static/` → proxy hacia `backend:8000`. Las imágenes subidas se guardan en `media/productos/` (el nombre del archivo se deriva del nombre del producto en `Product.product_image_path`).

## Bot de WhatsApp (integrado)

Un bot de ventas por WhatsApp corre junto al e-commerce en el mismo `docker-compose.yml`. Servicios: **evolution-api** (gateway de WhatsApp, `127.0.0.1:8080`), **evolution-postgres** (BD propia de Evolution) + **redis** (su caché), y **n8n** (`127.0.0.1:5678`, el motor del bot: máquina de estados + agente LLM vía OpenRouter).

- **BD compartida con schemas:** el Postgres del e-commerce (`ecommerce_db`) tiene `public` (e-commerce), `bot_data` (dominio del bot: `users`, `chat_sessions`, `orders`, `tickets` + funciones `approve_payment`/etc.) y `n8n` (BD interna de n8n, vía `DB_POSTGRESDB_SCHEMA=n8n`). Evolution mantiene su **propio** Postgres aparte.
- **Catálogo = vista:** `bot_data.catalog` es una **VISTA** sobre `public.product` (`postgres/init/02_bot_schema.sql`). El agente del bot vende el catálogo real del e-commerce. `sku/stock/is_active` se sintetizan en la vista (no existen aún en `product`).
- **Lógica del bot:** vive en el workflow de n8n (id `GlC4IjxnLdfRBj3H`), importado desde `_integracion/Bot Híbrido_…json`. Editar en la UI de n8n y re-exportar, o vía CLI (`n8n export/import:workflow`). Flujo: WhatsApp → evolution-api → webhook `POST /webhook/whatsapp` en n8n → router → agente → evolution-api → WhatsApp.
- **Config:** Evolution lee `.env.evolution` (gitignored); las credenciales de n8n (Postgres + OpenRouter) están en el credential store de n8n. Los `.sql` del bot están en `postgres/init/` (se aplican solos en un volumen nuevo; en uno existente se aplican con `docker compose exec -T postgres psql -U ecommerce_user -d ecommerce_db < postgres/init/02_bot_schema.sql`).
- **Emparejar WhatsApp:** crear/conectar la instancia `test` en el manager de Evolution (`http://127.0.0.1:8080/manager`, apikey en `.env.evolution`) y escanear el QR.
- **Monitor de Ventas (panel admin homologado):** página `web/monitor_ventas.html` (solo ADMIN/SUPERADMIN) con 3 columnas (usuarios | órdenes | chat WhatsApp), botones Aprobar/Rechazar pago y Resolver reclamo, y un compositor para **enviar mensajes de texto** al cliente (`POST /api/bot/chat/send/` → Evolution `sendText` con `settings.EVOLUTION_API_*`, se registra como `ADMIN` en `chat_messages`). Backend en `backend/shop/bot_views.py` bajo `/api/bot/*` (SQL crudo sobre `bot_data`, permiso `IsAdminRole`). El comprobante de pago se persiste: el nodo n8n **"Guardar Comprobante"** (rama de pago) hace POST a `/api/bot/payment-proof/` (header `X-Bot-Token` = `settings.BOT_INTERNAL_TOKEN`), que guarda la imagen en `media/comprobantes/<order_id>.<ext>` y setea `orders.payment_proof_url`.

## Notas

- Seguridad: la config sensible está externalizada a `.env` (ver "Configuración"). `DEBUG`, `SECRET_KEY`, CORS y `ALLOWED_HOSTS` se controlan por env; hay throttling en el login. Pendiente para producción: TLS y rotar la `SECRET_KEY` (la actual venía del repo).
- Los precios son enteros en "soles" (`S/`); `Product.price` es un `BigIntegerField`.
- Hay varios servicios comentados en `docker-compose.yml` y `nginx/default.conf` (IDE code-server, túnel cloudflared) — están desactivados a propósito, no es configuración muerta para borrar sin pensar.
