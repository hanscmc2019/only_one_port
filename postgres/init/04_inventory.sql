-- ============================================================
--  Inventario: mantiene el stock actual (denormalizado) y el costo
--  a partir del kardex (tienda."Inventory"). Cada movimiento insertado
--  ajusta el stock del producto o de la variante por `quantity` (con signo),
--  y un INGRESO con costo actualiza product.cost (valorización a último costo).
--  Así toda entrada/salida (página inventario, ventas, etc.) queda consistente
--  sin duplicar lógica en cada lugar que inserta movimientos.
-- ============================================================

CREATE OR REPLACE FUNCTION tienda.apply_inventory_movement()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.id_variant IS NOT NULL THEN
    UPDATE tienda.product_variant
       SET stock = stock + NEW.quantity
     WHERE id = NEW.id_variant;
  ELSE
    UPDATE tienda.product
       SET stock = stock + NEW.quantity
     WHERE id = NEW.id_product;
  END IF;

  -- Valorización: el último INGRESO con costo fija el costo unitario del producto.
  IF NEW.movement_type = 'INGRESO' AND NEW.unit_cost IS NOT NULL THEN
    UPDATE tienda.product SET cost = NEW.unit_cost WHERE id = NEW.id_product;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_inventory_apply
AFTER INSERT ON tienda."Inventory"
FOR EACH ROW EXECUTE FUNCTION tienda.apply_inventory_movement();
