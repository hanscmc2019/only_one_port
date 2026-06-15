-- ============================================================
--  Esquema del bot de WhatsApp (integrado al Postgres del e-commerce)
--  Adaptado de _integracion/init_bot_schema.sql.
--  Diferencia clave: bot_data.catalog es una VISTA sobre public.product
--  (el bot vende el catálogo real del e-commerce), no una tabla propia.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS bot_data;

-- Schema para la BD interna de n8n (n8n crea sus tablas aquí vía DB_POSTGRESDB_SCHEMA=n8n)
CREATE SCHEMA IF NOT EXISTS n8n;

-- Tabla de usuarios (clientes del bot)
CREATE TABLE IF NOT EXISTS bot_data.users (
    id SERIAL PRIMARY KEY,
    phone VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Máquina de estados de las sesiones de chat
CREATE TABLE IF NOT EXISTS bot_data.chat_sessions (
    user_id INTEGER PRIMARY KEY REFERENCES bot_data.users(id),
    current_state VARCHAR(50) DEFAULT 'BOT_ACTIVE', -- BOT_ACTIVE, PENDING_PAYMENT_APPROVAL, PAYMENT_IN_REVIEW, CLAIM_OPEN, HUMAN_TAKEOVER
    last_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Historial de mensajes (memoria del LLM y de la ticketera)
CREATE TABLE IF NOT EXISTS bot_data.chat_messages (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES bot_data.users(id),
    sender_type VARCHAR(20) NOT NULL, -- 'USER', 'BOT', 'ADMIN'
    content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Catálogo: VISTA sobre el catálogo real del e-commerce (public.product).
-- El agente solo usa: sku, name, description, price, stock, is_active.
-- sku/stock/is_active no existen en product → se sintetizan (ver plan; se harán reales luego).
CREATE OR REPLACE VIEW bot_data.catalog AS
SELECT p.id                       AS id,
       'PROD-' || p.id            AS sku,
       p.product_name             AS name,
       p.details                  AS description,
       p.price::numeric           AS price,
       9999                       AS stock,
       TRUE                       AS is_active
FROM public.product p;

-- Órdenes y cotizaciones
CREATE TABLE IF NOT EXISTS bot_data.orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES bot_data.users(id),
    items JSONB NOT NULL,
    total_amount NUMERIC(10, 2) NOT NULL,
    payment_proof_url TEXT,
    payment_operation_code VARCHAR(100),
    status VARCHAR(50) DEFAULT 'PENDING', -- PENDING, PAID, CANCELLED
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Ticketera para administradores
CREATE TABLE IF NOT EXISTS bot_data.tickets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES bot_data.users(id),
    order_id INTEGER REFERENCES bot_data.orders(id),
    ticket_type VARCHAR(50) NOT NULL, -- PAYMENT_VALIDATION, CLAIM
    status VARCHAR(50) DEFAULT 'OPEN', -- OPEN, IN_PROGRESS, CLOSED
    admin_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
