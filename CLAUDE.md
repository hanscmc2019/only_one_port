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

- Solo nginx está publicado (puerto del host `WEB_PORT`, por defecto `8090:80`). `postgres` y `backend` solo son accesibles dentro de la red del stack; el frontend siempre habla con la API a través de nginx por rutas relativas `/api/`, nunca con un host/puerto fijo. (Evolution y n8n se publican solo en `127.0.0.1` vía `EVOLUTION_PORT`/`N8N_PORT`.)
- El contenedor del backend monta `./backend` y `./media` como volúmenes, así que los cambios en Python los recoge el autoreload de Django sin reconstruir. Solo reconstruir cuando cambian `requirements.txt` o el Dockerfile.
- `backend/entrypoint.sh` ejecuta `migrate`, `collectstatic` (estáticos del admin vía WhiteNoise) y vuelve a sembrar usuarios/grupos en cada arranque del contenedor (es idempotente).

### Configuración (`.env`)

**Hay un único `.env`** (en la raíz, **ignorado por git**) que es la fuente de verdad de toda la config sensible del stack — Django, ambos Postgres, Evolution y n8n. No hay credenciales hardcodeadas en `docker-compose.yml`: este referencia las variables con `${VAR}` (interpolación del `.env` que Compose carga automáticamente), y el `backend` además inyecta el `.env` completo vía `env_file` (Django lo lee con `os.environ`). `.env.example` es una **plantilla versionada solo para documentar** las variables — no se usa en ejecución (`cp .env.example .env` para arrancar de cero).

- **Gotcha:** los `$` en valores del `.env` deben escaparse como `$$` (docker-compose interpola `$`).
- **Multi-cliente (`CLIENT_NAME`):** el nombre de los contenedores, la red y los volúmenes nombrados llevan el prefijo `${CLIENT_NAME}`, y los puertos del host son variables (`WEB_PORT`, `EVOLUTION_PORT`, `N8N_PORT`). Así varios stacks (uno por cliente, cada uno en su propia copia del repo) conviven en el mismo servidor sin colisionar. **Cambiar `CLIENT_NAME` reapunta a volúmenes nuevos y vacíos** (WhatsApp se desempareja, n8n se reinicia); para este stack vale `only_one_port` porque así coincide con los volúmenes ya existentes.
- **`N8N_ENCRYPTION_KEY`:** clave de cifrado de las credenciales de n8n; está fijada en el `.env` (antes la auto-generaba n8n solo en su volumen). **No cambiarla**: si cambia, n8n no puede descifrar las credenciales guardadas (OpenRouter, Postgres) y hay que recrearlas.
- **`EVOLUTION_API_KEY`** es la única clave de Evolution: el compose la mapea a `AUTHENTICATION_API_KEY` (Evolution) y `settings.py` la usa para enviar mensajes desde el panel. Antes estaba duplicada en un `.env.evolution` aparte (ya eliminado).
- Generar una `SECRET_KEY` nueva y pegarla en la variable `SECRET_KEY` del `.env`:
  ```bash
  docker compose exec backend python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
  ```
- **Zona horaria (`TZ`, por defecto `America/Lima`):** el stack corre en hora local, no UTC. El compose pasa `TZ` a **postgres** (como `timezone` del servidor vía `command: -c timezone=$TZ`, que fija la hora de pared que guardan las columnas `timestamp` por `CURRENT_TIMESTAMP`/`NOW()`) y a **backend** (reloj del contenedor). En `settings.py`: `TIME_ZONE = os.environ.get('TZ', 'America/Lima')` y **`USE_TZ = False`** → Django guarda y devuelve fechas naïve en hora local, alineado con Postgres; el frontend solo recorta el ISO, así que muestra hora de Perú. nginx **no** interviene en las fechas. Perú es UTC-5 fijo (sin DST). **Gotcha:** las filas creadas antes de este cambio quedaron en UTC y se ven 5 h adelantadas (eran datos de prueba). Cambiar `TZ` requiere recrear los contenedores (`docker compose up -d postgres backend`), no solo `restart`.
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

**Tres schemas de Postgres** (un solo `ecommerce_db`): `public` = framework Django (`auth_*`, `django_*`, sesiones, `cart`, `cart_item`); `tienda` = dominio del negocio + bot unidos (`category`, `product`, `product_variant`, `Inventory`, `orders`, `users`, `chat_sessions`, `chat_messages`, `tickets`, vista `catalog`, + las 4 funciones de acción); `n8n` = BD interna de n8n. Django resuelve `tienda` vía `search_path=public,tienda` en las `OPTIONS` de la conexión (`settings.py`), así los modelos `managed=False` no llevan prefijo y las tablas que Django crea (`cart`/`cart_item`/sistema) caen en `public`.

**Productos, precios, stock y variantes (multi-sector):** `product` tiene **dos precios** — `price_retail` (por menor / normal, principal) y `price_wholesale` (por mayor / con descuento, opcional) — y `stock` (entero). El **tipo de negocio** lo fija `STORE_TYPE` en el `.env` (`variants` = ropa con talla/color, `simple` = cosméticos sin variantes); como el frontend estático no lee el `.env`, lo expone el endpoint público **`/api/config/`** (deriva también la etiqueta del 2º precio). En tiendas `variants`, cada producto tiene filas en `tienda.product_variant` (`size`, `color`, `stock`; UNIQUE(id_product,size,color)) y el stock disponible = suma de variantes; en `simple` el stock vive en `product.stock`. Las variantes **no** tienen precio propio (heredan los del producto). La vista `tienda.catalog` expone `price_retail`, `price_wholesale`, el `stock` real (COALESCE suma-variantes/product.stock) y `variants` (JSON talla/color/stock o NULL).

**Inventario / kardex (control de stock):** `tienda."Inventory"` es el **libro de movimientos** (no un stock manual): cada fila es un movimiento `{id_product, id_variant?, movement_type (INGRESO/AJUSTE/MERMA/DEVOLUCION/VENTA), quantity (delta con signo), unit_cost, note}`. Un **trigger** (`postgres/init/04_inventory.sql`) mantiene `product.stock`/`product_variant.stock` (y, en INGRESO con costo, `product.cost`) desde cada movimiento → así toda entrada/salida es consistente y queda trazada. Por eso `stock` y `cost` son **read-only** en los serializers de producto/variante: el stock **solo** cambia insertando movimientos. La página **`web/inventario.html`** (solo ADMIN) gestiona esto: a la izquierda un **árbol desplegable** (categoría → producto → talla/color en `variants`, solo hasta producto en `simple`) donde cada nodo muestra a la derecha su **stock actual** y al hacer clic filtra el kardex y preselecciona el ítem en el formulario; al medio el formulario de movimiento manual; a la derecha el kardex. El árbol se arma con `/api/inventory/stock/` (que ahora incluye `id_category`/`category_name`) + `/api/categories/`, y se reconstruye tras cada movimiento conservando la expansión/selección. Barra de **valorización** (unidades y valor S/ = Σ stock×costo) y **exportar CSV** (stock/kardex). Endpoints (admin, `IsAdminRole`): `/api/inventory/` (CRUD de movimientos, filtros `?id_product=&id_variant=&id_category=&movement_type=&date_from=&date_to=`), `/api/inventory/stock/` (stock+valorización), `/api/inventory/export/?kind=stock|kardex`. **El catálogo (`web/catalogo.html`) NO gestiona stock**: solo crea productos, precios y variantes (talla/color); todo el stock — incluido el inicial — se inicia en Inventario. **Las ventas descuentan stock**: `tienda.approve_payment` inserta un movimiento `VENTA` por ítem de la orden al aprobar el pago (visible como SALIDA en el kardex).

**Ventas manuales (página Ventas):** `web/ventas.html` (solo ADMIN) permite al admin registrar una venta de mostrador/teléfono. Layout 3 columnas (4/4/4): izquierda un formulario (cliente nombre/nro opcionales; categoría y producto como `<datalist>` autocompletables que deben resolver a un id registrado; talla/color solo en `STORE_TYPE=variants`; cantidad; precio unitario autocompletado con `price_retail` y **editable**) con botón **Agregar** que arma el carrito; al medio la tabla del carrito con **Total** y el botón **"Venta realizada"**; a la derecha el filtro (botón "Todos" + combos categoría/producto) y la tabla de **últimas ventas**. El cierre hace `POST /api/sales/` (`ManualSaleView`, `IsAdminRole`): valida stock, **inserta la orden en `tienda.orders` con `status='PENDING'`, `user_id=NULL` y el cliente suelto en las columnas `customer_name`/`customer_phone`** (no se enlaza a `tienda.users`), y reusa `tienda.approve_payment(order_id)` para marcarla `PAID` e insertar los movimientos `VENTA` (el trigger baja el stock). Como `user_id` queda NULL, **estas ventas NO aparecen en el Monitor de Ventas** (su `ORDERS_SQL` hace INNER JOIN a `users`), pero sí en el kardex. La tabla **"Últimas ventas"** (derecha) lee de `GET /api/sales/recent/` (`RecentSalesView`, admin): devuelve las órdenes `PAID` (bot + manuales) **agrupadas por orden** (N° orden + cliente con rowspan; una fila por ítem con producto, talla/color, cantidad y subtotal). Acepta `?id_category=&id_product=` que recortan a los ítems coincidentes (la orden se omite si no le queda ninguno); el cliente sale de `customer_name` o, si es del bot, del `name`/`phone` de `users`.

El esquema de `tienda` está definido en **dos lugares** y deben mantenerse sincronizados manualmente:

- `postgres/init/01_schema.sql` crea `tienda.category`, `tienda.product` y `tienda."Inventory"`; `02_bot_schema.sql` crea las tablas del bot + la vista `catalog` + `tienda.orders`; `03_bot_functions.sql` las funciones. Solo se ejecutan **cuando el volumen de datos de postgres está vacío** (init del entrypoint de Docker). Para volver a aplicarlo hay que borrar `./postgres_data` y reiniciar.
- En `backend/shop/models.py`, `Category`, `Product` e `Inventory` son `managed = False` — mapean sobre las tablas del SQL (en `tienda`, resuelto por `search_path`) y Django **no** genera ni aplica migraciones para ellas. Cambiar estos modelos no cambia la BD; en su lugar hay que editar el `.sql` (y resetear el volumen).
- `Cart` y `CartItem` son `managed = True` (migraciones normales de Django en `backend/shop/migrations/`, creadas en `public`).
- **Órdenes unificadas:** `tienda.orders` (JSONB `items`, total, comprobante, estado) es la fuente de verdad única para cualquier canal (bot u otro). Reemplazó a la antigua tabla muerta `sale`, que se eliminó junto con su stack Django (modelo `Sale`, serializer, viewset y ruta `sales/`).

### Superficie de la API

`core/urls.py` monta la autenticación en `/api/login/` + `/api/token/refresh/` (SimpleJWT) e incluye `shop/urls.py` bajo `/api/`:

- `config/` — `APIView` pública (`AllowAny`) que devuelve `{store_type, show_variants, price_wholesale_label}` desde `settings.STORE_TYPE`. El frontend la consulta al cargar (`web/js/load_components.js` → `window.STORE_CONFIG` vía `getStoreConfig()`) para mostrar/ocultar el selector de variantes y rotular el 2º precio.
- `categories/`, `products/` — `ModelViewSet`s de DRF. `products/` acepta `?id_category=<id>` y `?search=<texto>`. `products/` incluye `variants` (anidado, solo lectura). Todas las listas soportan paginación opcional `?limit=&offset=` (sin esos params devuelven lista plana).
- `variants/` — `ModelViewSet` de variantes de producto (lectura abierta, escritura admin), filtro `?id_product=<id>`. Lo usa el editor de variantes del catálogo (`catalogo.html`, solo visible si `show_variants`; pide solo talla/color, no stock ni precio). `stock` es read-only (cambia solo por movimientos de inventario).
- `cart/`, `cart/add/`, `cart/update/<id>/`, `cart/remove/<id>/` — `APIView`s simples. `cart/add/` acepta `variant_id` opcional; los ítems del carrito se identifican por `(cart, product, variant)`.
- `checkout/whatsapp/` — construye una URL `wa.me` con el contenido del carrito (número desde `settings.WHATSAPP_PHONE` / env).
- `inventory/`, `inventory/stock/`, `inventory/export/` — **solo admin**: kardex de movimientos, stock+valorización y export CSV (ver "Inventario / kardex" arriba).
- `sales/` — `POST` **solo admin** (`ManualSaleView` en `bot_views.py`): venta manual del admin (ver "Ventas manuales" abajo).

### Identidad del carrito (invitado vs. autenticado)

`get_cart()` en `shop/views.py` es la única fuente de verdad. Las peticiones autenticadas obtienen un carrito por `user`; las anónimas se identifican por la cabecera `X-Guest-ID`. El frontend genera y guarda ese id en `localStorage` y lo adjunta a **todas** las llamadas AJAX mediante un `$.ajaxSetup` global con `beforeSend` (ver `web/js/main.js`), junto con la cabecera `Authorization: Bearer` cuando existe un token. Al iniciar sesión, `merge_guest_cart()` fusiona el carrito de invitado (por `X-Guest-ID`) en el del usuario.

### Autorización / roles

Los roles son **Groups** de Django: `SUPERADMIN`, `ADMIN`, `CUSTOMER`, sembrados por `entrypoint.sh`. Los usuarios (username/email/password de cada rol) se configuran por `.env` con las variables `SEED_<ROL>_*` (defaults de desarrollo: `superadmin/admin123`, `admin/admin123`, `cliente/cliente123`). La contraseña **solo se fija al crear** el usuario (primer arranque con BD vacía); en arranques posteriores no se pisa (para no revertir un cambio hecho en el admin de Django o con `manage.py changepassword`), pero los flags `is_staff`/`is_superuser` sí se reafirman siempre. En `shop/views.py`: `IsAdminRoleOrReadOnly` deja la lectura abierta y restringe la escritura de productos/categorías a superusuarios o grupos ADMIN/SUPERADMIN; `IsAdminRole` exige admin para **todos** los métodos (ventas/inventario, no públicos). `CustomTokenObtainPairSerializer` agrega `username`, `email` y `roles` a la respuesta del login; el frontend los guarda en `localStorage` y aplica el control de acceso a nivel de UI en `web/js/load_components.js`. El login está limitado a 5/min por IP (DRF throttling, scope `login`).

### Frontend

`web/` es una plantilla estática de Bootstrap 4 + jQuery (sin paso de build para el HTML/JS). El chrome compartido se carga por componentes:

- `web/components/topbar.html` / `navbar.html` / `footer.html` se inyectan en tiempo de ejecución por `web/js/load_components.js` dentro de `#topbar-placeholder` / `#navbar-placeholder` / `#footer-placeholder`, que luego aplica la UI según rol (ocultar los links de admin como catálogo/inventario/monitor, cambiar los botones de login, auto-logout de admin por inactividad).
- El CSS no tiene paso de build: se edita `web/css/style.css` directamente. Los colores/tamaños de marca están tokenizados como variables CSS (`--brand-*`) y se configuran en `web/css/theme.css` (cargado después de `style.css`), que es el único archivo que el programador edita para re-skinnear el sitio.

### Ruteo de nginx (`nginx/default.conf`)

`/` → estático `web/`; `/media/` → imágenes de productos subidas; `/api/`, `/admin/`, `/static/` → proxy hacia `backend:8000`. Las imágenes subidas se guardan en `media/productos/` (el nombre del archivo se deriva del nombre del producto en `Product.product_image_path`).

## Bot de WhatsApp (integrado)

Un bot de ventas por WhatsApp corre junto al e-commerce en el mismo `docker-compose.yml`. Servicios: **evolution-api** (gateway de WhatsApp, `127.0.0.1:8080`), **evolution-postgres** (BD propia de Evolution) + **redis** (su caché), y **n8n** (`127.0.0.1:5678`, el motor del bot: máquina de estados + agente LLM vía OpenRouter).

- **BD compartida con schemas:** el Postgres del e-commerce (`ecommerce_db`) tiene `public` (framework Django), `tienda` (negocio + bot unidos: `product`, `category`, `Inventory`, `orders`, `users`, `chat_sessions`, `chat_messages`, `tickets` + funciones `approve_payment`/etc.) y `n8n` (BD interna de n8n, vía `DB_POSTGRESDB_SCHEMA=n8n`). Evolution mantiene su **propio** Postgres aparte.
- **Catálogo = vista:** `tienda.catalog` es una **VISTA** sobre `tienda.product` (+ `product_variant`) en `postgres/init/02_bot_schema.sql`. Expone `price_retail`, `price_wholesale`, `stock` real (suma de variantes o `product.stock`), `is_active` (= stock>0), `variants` (JSON talla/color/stock o NULL) y `sku` sintetizado. El prompt del bot lee estos campos: usa `price_retail` como precio unitario, menciona `price_wholesale` y, si el producto trae `variants`, pide talla/color y valida el stock de esa variante (incluyendo `size`/`color` en los ítems de la orden).
- **Lógica del bot:** vive en el workflow de n8n (id `GlC4IjxnLdfRBj3H`). La copia **versionada** (saneada, sin secretos) está en `n8n/workflows/bot-hibrido.json` y es la semilla para inicializar clientes nuevos (ver README, sección "inicializar un cliente nuevo"). Editar en la UI de n8n y re-exportar, o vía CLI (`n8n export/import:workflow`); al re-exportar para versionar, sanear los secretos (la apikey de Evolution queda como placeholder `__SET_EVOLUTION_API_KEY__`). Flujo: WhatsApp → evolution-api → webhook `POST /webhook/whatsapp` en n8n → router → agente → evolution-api → WhatsApp.
- **Auto-siembra del workflow + credenciales (sin pasos manuales):** el contenedor n8n usa un `entrypoint` propio (`n8n/seed/init.sh`, montado vía `./n8n:/opt/n8n-seed:ro`). En cada arranque, **si el schema `n8n` no tiene el workflow** (p. ej. volumen recién creado), `n8n/seed/gen.js` genera el workflow con la apikey de Evolution inyectada y las **3 credenciales** (Postgres, OpenRouter header, OpenAI/OpenRouter — IDs **fijos** que deben coincidir con los que referencia el JSON del workflow) a partir del `.env`, las importa con `n8n import:credentials/import:workflow` (n8n las re-cifra con `N8N_ENCRYPTION_KEY`) y activa el workflow. Es **idempotente**: si el workflow ya existe **no** reimporta (no pisa ediciones hechas en la UI), y la siembra es **no-fatal** (si falta `OPENROUTER_API_KEY` u otra var, n8n arranca igual y avisa; corrige el `.env` y reinicia). Requiere `EVOLUTION_API_KEY` y `OPENROUTER_API_KEY` en el `.env` (el compose se las pasa al contenedor por `environment:`; Postgres se reusa de las `DB_POSTGRESDB_*`). El `entrypoint` corre como root **solo** para hacer `chown` del bind-mount `./n8n_data` (Docker lo crea como root) y baja a `node` (uid 1000) con `su` antes de arrancar — necesario porque los volúmenes son carpetas del host, no volúmenes nombrados.
- **Owner auto-creado (sin formulario de setup):** n8n 2.x **ya no permite desactivar el login** (`N8N_USER_MANAGEMENT_DISABLED` fue removido y se ignora). En su lugar, `init.sh` crea el owner en cada arranque fresco llamando en segundo plano a `POST /rest/owner/setup` (la misma API que la pantalla de setup) con `N8N_OWNER_EMAIL`/`N8N_OWNER_PASSWORD` del `.env` (default `admin@n8n.local` / `Admin1234`; la contraseña requiere min 8, 1 mayúscula y 1 número). Es idempotente (solo crea el owner si `showSetupOnFirstLoad` sigue en true). Así no se rellena el formulario a mano: se entra con ese login fijo.
- **Config:** Evolution se configura desde el `.env` único (el compose le pasa las variables como `environment:`); las credenciales de n8n (Postgres + OpenRouter) viven en el credential store de n8n (schema `n8n`), cifradas con `N8N_ENCRYPTION_KEY` (ver "Configuración") y se auto-siembran desde el `.env` (ver punto anterior). Los `.sql` del bot están en `postgres/init/` (se aplican solos en un volumen nuevo; en uno existente se aplican con `docker compose exec -T postgres psql -U ecommerce_user -d ecommerce_db < postgres/init/02_bot_schema.sql`).
- **Emparejar WhatsApp:** crear/conectar la instancia `test` en el manager de Evolution (`http://127.0.0.1:8080/manager`, apikey = `EVOLUTION_API_KEY` del `.env`) y escanear el QR.
- **Monitor de Ventas (panel admin homologado):** página `web/monitor_ventas.html` (solo ADMIN/SUPERADMIN) con 3 columnas (usuarios | órdenes | chat WhatsApp), botones Aprobar/Rechazar pago y Resolver reclamo, y un compositor para **enviar mensajes de texto** al cliente (`POST /api/bot/chat/send/` → Evolution `sendText` con `settings.EVOLUTION_API_*`, se registra como `ADMIN` en `chat_messages`). Backend en `backend/shop/bot_views.py` bajo `/api/bot/*` (SQL crudo sobre `tienda`, permiso `IsAdminRole`). El comprobante de pago se persiste: el nodo n8n **"Guardar Comprobante"** (rama de pago) hace POST a `/api/bot/payment-proof/`, que guarda la imagen en `media/comprobantes/<order_id>.<ext>` y setea `orders.payment_proof_url`. Ese endpoint no exige autenticación (n8n lo llama por la red interna, `backend:8000`); **nginx bloquea `/api/bot/payment-proof/` desde el exterior** (`deny all; return 404`), así que no es accesible públicamente.

## Notas

- Seguridad: la config sensible está externalizada a `.env` (ver "Configuración"). `DEBUG`, `SECRET_KEY`, CORS y `ALLOWED_HOSTS` se controlan por env; hay throttling en el login. Pendiente para producción: TLS y rotar la `SECRET_KEY` (la actual venía del repo).
- Los precios son enteros en "soles" (`S/`); `Product.price` es un `BigIntegerField`.
- Hay varios servicios comentados en `docker-compose.yml` y `nginx/default.conf` (IDE code-server, túnel cloudflared) — están desactivados a propósito, no es configuración muerta para borrar sin pensar.
