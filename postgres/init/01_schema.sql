-- ====================================
-- Schema inicial para E-Commerce
-- ====================================

CREATE TABLE IF NOT EXISTS productos (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(255) NOT NULL,
    descripcion TEXT,
    precio DECIMAL(10, 2) NOT NULL,
    stock INTEGER DEFAULT 0,
    imagen_url VARCHAR(500),
    categoria VARCHAR(100),
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    nombre VARCHAR(255),
    telefono VARCHAR(20),
    direccion TEXT,
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pedidos (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER REFERENCES usuarios(id),
    total DECIMAL(10, 2) NOT NULL,
    estado VARCHAR(50) DEFAULT 'pendiente',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS detalle_pedido (
    id SERIAL PRIMARY KEY,
    pedido_id INTEGER REFERENCES pedidos(id),
    producto_id INTEGER REFERENCES productos(id),
    cantidad INTEGER NOT NULL,
    precio_unitario DECIMAL(10, 2) NOT NULL
);

-- Datos de ejemplo
INSERT INTO productos (nombre, descripcion, precio, stock, categoria) VALUES
    ('Laptop Gaming', 'Laptop de alto rendimiento para gaming', 2999.99, 10, 'Computadoras'),
    ('Mouse Inalámbrico', 'Mouse ergonómico wireless', 49.99, 50, 'Accesorios'),
    ('Teclado Mecánico', 'Teclado mecánico RGB', 129.99, 30, 'Accesorios'),
    ('Monitor 4K', 'Monitor 27 pulgadas 4K HDR', 599.99, 15, 'Monitores'),
    ('Audífonos Bluetooth', 'Audífonos over-ear con cancelación de ruido', 199.99, 25, 'Audio');
