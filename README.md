# Tienda e-commerce + Bot de WhatsApp (dockerizado)

Tienda online para una tienda peruana, con checkout por WhatsApp y un **bot de ventas** por WhatsApp integrado. Todo el stack corre con Docker Compose.

Servicios: **nginx** (sirve el frontend estático y hace de reverse proxy), **postgres** (datos), **backend** (API REST de Django), **evolution-api** + **evolution-postgres** + **redis** (gateway de WhatsApp), y **n8n** (motor del bot).

> Para la arquitectura en detalle (modelo de datos, endpoints, roles, integración del bot) ver [`CLAUDE.md`](CLAUDE.md).

---

## Requisitos

- Docker y Docker Compose v2.

## Puesta en marcha

```bash
cp .env.example .env        # crear el .env y rellenar valores (ver "Secretos" abajo)
docker compose up --build   # levanta todo; sitio en http://localhost:8090
```

- Sitio público: `http://localhost:<WEB_PORT>` (por defecto `8090`).
- Editor de n8n: `http://127.0.0.1:<N8N_PORT>` (por defecto `5678`, solo localhost).
- Manager de Evolution: `http://127.0.0.1:<EVOLUTION_PORT>/manager` (por defecto `8080`, solo localhost).

```bash
docker compose down                 # detener
docker compose logs -f backend      # ver logs
```

---

## Configuración y secretos (`.env`)

Hay **un único `.env`** (gitignored) que es la fuente de verdad de toda la config sensible. `docker-compose.yml` referencia las variables con `${VAR}`; no hay credenciales hardcodeadas en el compose. [`.env.example`](.env.example) es la plantilla versionada (solo documenta; no se usa en ejecución).

> **Gotcha:** en el `.env`, cada `$` se escribe como `$$` (docker-compose interpola `$`).

### Secretos y cómo generarlos

| Variable | Qué es | Cómo generar |
|---|---|---|
| `SECRET_KEY` | Clave maestra de Django (firma sesiones, CSRF, tokens JWT). | ver abajo |
| `EVOLUTION_API_KEY` | Clave de la API de Evolution (única; el compose la mapea a `AUTHENTICATION_API_KEY`). | `openssl rand -hex 24` |
| `N8N_ENCRYPTION_KEY` | Cifra las credenciales guardadas en n8n (OpenRouter, Postgres). | `openssl rand -hex 16` |
| `POSTGRES_PASSWORD`, `EVOLUTION_POSTGRES_PASSWORD` | Contraseñas de las bases de datos. | `openssl rand -hex 16` |

#### `SECRET_KEY` (Django)

Es la clave que Django usa para firmar y cifrar datos sensibles: cookies de sesión, tokens CSRF, los JWT de la API y los links de reseteo de contraseña. **Quien la conozca puede falsificar sesiones y tokens**, por eso debe ser secreta y única por instalación.

La que trae el repo empieza con `django-insecure-`: es el placeholder que genera Django al crear el proyecto y **debe reemplazarse antes de producción**.

Generar una nueva (con el stack levantado):

```bash
docker compose exec backend python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Pegarla en `SECRET_KEY` del `.env`. **Importante:** escapar cada `$` como `$$`. Al rotarla se invalidan las sesiones y JWT activos (los usuarios deben volver a iniciar sesión).

#### `N8N_ENCRYPTION_KEY` (n8n)

n8n cifra con esta clave las credenciales que guardas en su credential store. **No la cambies en un stack existente**: si cambia, n8n no puede descifrar las credenciales ya guardadas y hay que recrearlas. Es un secreto **por cliente** (no se versiona); para un cliente nuevo se genera fresca con `openssl rand -hex 16`.

---

## Multi-cliente (varios stacks en un servidor)

El stack está parametrizado para correr **una instancia por cliente** en el mismo servidor sin colisiones:

- `CLIENT_NAME` prefija contenedores, red y volúmenes.
- `WEB_PORT`, `EVOLUTION_PORT`, `N8N_PORT` son los puertos del host (únicos por cliente).

Para un cliente nuevo: clonar el repo en otra carpeta, `cp .env.example .env`, y dar un `CLIENT_NAME` y puertos distintos + secretos frescos.

> **Cuidado:** cambiar `CLIENT_NAME` en un stack ya existente reapunta a volúmenes nuevos y vacíos (WhatsApp se desempareja, n8n se reinicia).

---

## Bot de WhatsApp — inicializar un cliente nuevo

Lo que se **versiona en el repo** (la fuente para sembrar clientes) es el **workflow** del bot ([`n8n/workflows/bot-hibrido.json`](n8n/workflows/), saneado, sin secretos) y el esquema SQL ([`postgres/init/`](postgres/init/)). Las credenciales (OpenRouter, apikey de Evolution) son **por cliente** y se crean en cada instalación, no se versionan.

Pasos para un cliente nuevo:

1. `.env` con secretos frescos (incl. `N8N_ENCRYPTION_KEY` y `EVOLUTION_API_KEY` propios) y las credenciales iniciales de los usuarios (`SEED_SUPERADMIN_*`, `SEED_ADMIN_*`, `SEED_CUSTOMER_*`); luego `docker compose up -d`. Esas contraseñas se aplican en el **primer arranque** (BD vacía); después se administran desde el admin de Django.
2. Importar el workflow:
   ```bash
   docker compose cp n8n/workflows/bot-hibrido.json n8n:/tmp/wf.json
   docker compose exec n8n n8n import:workflow --input=/tmp/wf.json
   docker compose exec n8n n8n update:workflow --id=<ID> --active=true
   docker compose restart n8n
   ```
3. En la UI de n8n: poner la `EVOLUTION_API_KEY` real en los nodos HTTP (reemplaza el placeholder `__SET_EVOLUTION_API_KEY__`) y crear la credencial de OpenRouter.
4. Emparejar WhatsApp: crear/conectar la instancia en el manager de Evolution y escanear el QR.

---

## Comandos útiles

```bash
# Migraciones / superusuario
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser

# Aplicar SQL del bot en un volumen existente
docker compose exec -T postgres psql -U ecommerce_user -d ecommerce_db < postgres/init/02_bot_schema.sql

# Exportar el workflow tras editarlo en la UI (para re-versionarlo, sin secretos)
docker compose exec n8n n8n export:workflow --id=<ID> --output=/tmp/wf.json
```
