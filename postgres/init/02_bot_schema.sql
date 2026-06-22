-- ============================================================
--  Tablas del bot de WhatsApp, unidas al dominio del negocio en el
--  schema `tienda` (antes vivían en un schema `bot_data` aparte).
--  Al estar junto a product/Inventory, el bot ve el catálogo y el
--  stock sin FKs cruzados entre schemas.
--  tienda.catalog es una VISTA sobre tienda.product (el bot vende el
--  catálogo real del e-commerce), no una tabla propia.
-- ============================================================

-- El schema `tienda` ya se crea en 01_schema.sql.

-- Schema para la BD interna de n8n (n8n crea sus tablas aquí vía DB_POSTGRESDB_SCHEMA=n8n)
CREATE SCHEMA IF NOT EXISTS n8n;

-- Tabla de usuarios (clientes del bot)
CREATE TABLE IF NOT EXISTS tienda.users (
    id SERIAL PRIMARY KEY,
    phone VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Máquina de estados de las sesiones de chat
CREATE TABLE IF NOT EXISTS tienda.chat_sessions (
    user_id INTEGER PRIMARY KEY REFERENCES tienda.users(id),
    current_state VARCHAR(50) DEFAULT 'BOT_ACTIVE', -- BOT_ACTIVE, PENDING_PAYMENT_APPROVAL, PAYMENT_IN_REVIEW, CLAIM_OPEN, HUMAN_TAKEOVER
    last_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Historial de mensajes (memoria del LLM y de la ticketera)
CREATE TABLE IF NOT EXISTS tienda.chat_messages (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES tienda.users(id),
    sender_type VARCHAR(20) NOT NULL, -- 'USER', 'BOT', 'ADMIN'
    content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Catálogo: VISTA sobre el catálogo real del e-commerce (tienda.product).
-- Expone los 2 precios (menor/normal y mayor/descuento), el stock real y, para
-- productos con variantes, el arreglo `variants` (talla/color/stock). El stock
-- es la suma de las variantes si existen; si no, product.stock. `sku` se sintetiza.
CREATE OR REPLACE VIEW tienda.catalog AS
SELECT p.id                          AS id,
       'PROD-' || p.id               AS sku,
       p.product_name                AS name,
       p.details                     AS description,
       p.price_retail::numeric       AS price_retail,
       p.price_wholesale::numeric    AS price_wholesale,
       COALESCE(v.total_stock, p.stock)        AS stock,
       (COALESCE(v.total_stock, p.stock) > 0)  AS is_active,
       v.variants                    AS variants   -- JSON [{size,color,stock,sku}] o NULL
FROM tienda.product p
LEFT JOIN LATERAL (
  SELECT SUM(pv.stock) AS total_stock,
         jsonb_agg(jsonb_build_object(
           'size', pv.size, 'color', pv.color, 'stock', pv.stock, 'sku', pv.sku
         ) ORDER BY pv.size, pv.color) AS variants
  FROM tienda.product_variant pv
  WHERE pv.id_product = p.id
) v ON TRUE;

-- Órdenes y cotizaciones (fuente de verdad única; reemplaza la antigua `sale`).
-- Cualquier canal (bot u otro) crea órdenes aquí; a futuro descontará Inventory.
CREATE TABLE IF NOT EXISTS tienda.orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES tienda.users(id),  -- NULL en ventas manuales del admin (cliente suelto)
    items JSONB NOT NULL,
    total_amount NUMERIC(10, 2) NOT NULL,
    payment_proof_url TEXT,
    payment_operation_code VARCHAR(100),
    customer_name TEXT,   -- ventas manuales: nombre del cliente (opcional, sin enlazar a users)
    customer_phone TEXT,  -- ventas manuales: número del cliente (opcional)
    status VARCHAR(50) DEFAULT 'PENDING', -- PENDING, PAID, CANCELLED
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Ticketera para administradores
CREATE TABLE IF NOT EXISTS tienda.tickets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES tienda.users(id),
    order_id INTEGER REFERENCES tienda.orders(id),
    ticket_type VARCHAR(50) NOT NULL, -- PAYMENT_VALIDATION, CLAIM
    status VARCHAR(50) DEFAULT 'OPEN', -- OPEN, IN_PROGRESS, CLOSED
    admin_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
