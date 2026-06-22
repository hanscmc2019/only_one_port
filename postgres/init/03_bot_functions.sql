-- ============================================================
--  Funciones de acción del panel de administrador (atómicas).
--  Las usa el backend (shop/bot_views.py) y el agente del bot. Cada una
--  toca las tablas necesarias en una sola transacción para que el bot
--  nunca quede en un estado inconsistente. Viven en el schema `tienda`.
-- ============================================================

-- APROBAR pago: orden -> PAID | sesión -> BOT_ACTIVE | ticket -> CLOSED
--   + resetea la memoria del LLM (la conversación de esta compra termina aquí;
--     los próximos mensajes del cliente son una conversación nueva).
CREATE OR REPLACE FUNCTION tienda.approve_payment(p_order_id INT)
RETURNS VOID AS $$
DECLARE
  it           jsonb;
  v_product_id bigint;
  v_variant_id bigint;
  v_qty        integer;
BEGIN
  UPDATE tienda.orders SET status = 'PAID' WHERE id = p_order_id;

  UPDATE tienda.chat_sessions s
     SET current_state = 'BOT_ACTIVE', last_interaction = NOW()
    FROM tienda.orders o
   WHERE o.id = p_order_id AND s.user_id = o.user_id;

  UPDATE tienda.tickets
     SET status = 'CLOSED',
         admin_notes = COALESCE(admin_notes, '') || ' | APROBADO ' || NOW()
   WHERE order_id = p_order_id AND ticket_type = 'PAYMENT_VALIDATION' AND status <> 'CLOSED';

  -- Descontar inventario: un movimiento VENTA por cada ítem de la orden (el trigger
  -- de Inventory baja el stock). El sku es 'PROD-<id>'; talla/color resuelven la variante.
  FOR it IN SELECT jsonb_array_elements(items) FROM tienda.orders WHERE id = p_order_id
  LOOP
    v_product_id := NULLIF(regexp_replace(COALESCE(it->>'sku',''), '\D', '', 'g'), '')::bigint;
    v_qty := COALESCE((it->>'qty')::int, 0);
    IF v_product_id IS NULL OR v_qty <= 0 THEN
      CONTINUE;
    END IF;

    v_variant_id := NULL;
    IF (it ? 'size') OR (it ? 'color') THEN
      SELECT pv.id INTO v_variant_id
        FROM tienda.product_variant pv
       WHERE pv.id_product = v_product_id
         AND pv.size  IS NOT DISTINCT FROM NULLIF(it->>'size','')
         AND pv.color IS NOT DISTINCT FROM NULLIF(it->>'color','')
       LIMIT 1;
    END IF;

    INSERT INTO tienda."Inventory" (id_product, id_variant, movement_type, quantity, unit_cost, note)
    VALUES (v_product_id, v_variant_id, 'VENTA', -v_qty,
            NULLIF(it->>'price','')::numeric, 'Venta orden #' || p_order_id);
  END LOOP;

  -- Resetea la memoria del LLM. La tabla la crea n8n al primer mensaje; si aún no
  -- existe, no hay nada que limpiar (no debe abortar el resto del descuento de stock).
  BEGIN
    DELETE FROM public.n8n_chat_histories
     WHERE session_id = (SELECT u.phone FROM tienda.users u
                         JOIN tienda.orders o ON o.user_id = u.id WHERE o.id = p_order_id);
  EXCEPTION WHEN undefined_table THEN NULL;
  END;
END;
$$ LANGUAGE plpgsql;

-- CANCELAR la orden pendiente del cliente (la usa la tool cancelar_orden del agente):
--   órdenes PENDING -> CANCELLED | sesión -> BOT_ACTIVE | resetea memoria del LLM.
CREATE OR REPLACE FUNCTION tienda.cancel_pending_order(p_user_id INT)
RETURNS VOID AS $$
BEGIN
  UPDATE tienda.orders SET status = 'CANCELLED'
   WHERE user_id = p_user_id AND status = 'PENDING';

  INSERT INTO tienda.chat_sessions (user_id, current_state)
  VALUES (p_user_id, 'BOT_ACTIVE')
  ON CONFLICT (user_id) DO UPDATE SET current_state = 'BOT_ACTIVE', last_interaction = NOW();

  BEGIN
    DELETE FROM public.n8n_chat_histories
     WHERE session_id = (SELECT phone FROM tienda.users WHERE id = p_user_id);
  EXCEPTION WHEN undefined_table THEN NULL;
  END;
END;
$$ LANGUAGE plpgsql;

-- RECHAZAR pago: orden sigue PENDING | sesión -> PENDING_PAYMENT_APPROVAL | ticket -> CLOSED
CREATE OR REPLACE FUNCTION tienda.reject_payment(p_order_id INT)
RETURNS VOID AS $$
BEGIN
  UPDATE tienda.chat_sessions s
     SET current_state = 'PENDING_PAYMENT_APPROVAL', last_interaction = NOW()
    FROM tienda.orders o
   WHERE o.id = p_order_id AND s.user_id = o.user_id;

  UPDATE tienda.tickets
     SET status = 'CLOSED',
         admin_notes = COALESCE(admin_notes, '') || ' | RECHAZADO ' || NOW()
   WHERE order_id = p_order_id AND ticket_type = 'PAYMENT_VALIDATION' AND status <> 'CLOSED';
END;
$$ LANGUAGE plpgsql;

-- RESOLVER reclamo: ticket -> CLOSED | sesión -> BOT_ACTIVE
CREATE OR REPLACE FUNCTION tienda.resolve_claim(p_ticket_id INT)
RETURNS VOID AS $$
BEGIN
  UPDATE tienda.tickets
     SET status = 'CLOSED',
         admin_notes = COALESCE(admin_notes, '') || ' | RESUELTO ' || NOW()
   WHERE id = p_ticket_id AND ticket_type = 'CLAIM';

  UPDATE tienda.chat_sessions s
     SET current_state = 'BOT_ACTIVE', last_interaction = NOW()
    FROM tienda.tickets t
   WHERE t.id = p_ticket_id AND s.user_id = t.user_id;
END;
$$ LANGUAGE plpgsql;
