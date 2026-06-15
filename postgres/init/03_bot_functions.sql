-- ============================================================
--  Funciones de acción del panel de administrador (atómicas)
--  Las usa el backend FastAPI (admin/app.py). Cada una toca las
--  3 tablas necesarias en una sola transacción para que el bot
--  nunca quede en un estado inconsistente.
-- ============================================================

-- APROBAR pago: orden -> PAID | sesión -> BOT_ACTIVE | ticket -> CLOSED
--   + resetea la memoria del LLM (la conversación de esta compra termina aquí;
--     los próximos mensajes del cliente son una conversación nueva).
CREATE OR REPLACE FUNCTION bot_data.approve_payment(p_order_id INT)
RETURNS VOID AS $$
BEGIN
  UPDATE bot_data.orders SET status = 'PAID' WHERE id = p_order_id;

  UPDATE bot_data.chat_sessions s
     SET current_state = 'BOT_ACTIVE', last_interaction = NOW()
    FROM bot_data.orders o
   WHERE o.id = p_order_id AND s.user_id = o.user_id;

  UPDATE bot_data.tickets
     SET status = 'CLOSED',
         admin_notes = COALESCE(admin_notes, '') || ' | APROBADO ' || NOW()
   WHERE order_id = p_order_id AND ticket_type = 'PAYMENT_VALIDATION' AND status <> 'CLOSED';

  DELETE FROM public.n8n_chat_histories
   WHERE session_id = (SELECT u.phone FROM bot_data.users u
                       JOIN bot_data.orders o ON o.user_id = u.id WHERE o.id = p_order_id);
END;
$$ LANGUAGE plpgsql;

-- CANCELAR la orden pendiente del cliente (la usa la tool cancelar_orden del agente):
--   órdenes PENDING -> CANCELLED | sesión -> BOT_ACTIVE | resetea memoria del LLM.
CREATE OR REPLACE FUNCTION bot_data.cancel_pending_order(p_user_id INT)
RETURNS VOID AS $$
BEGIN
  UPDATE bot_data.orders SET status = 'CANCELLED'
   WHERE user_id = p_user_id AND status = 'PENDING';

  INSERT INTO bot_data.chat_sessions (user_id, current_state)
  VALUES (p_user_id, 'BOT_ACTIVE')
  ON CONFLICT (user_id) DO UPDATE SET current_state = 'BOT_ACTIVE', last_interaction = NOW();

  DELETE FROM public.n8n_chat_histories
   WHERE session_id = (SELECT phone FROM bot_data.users WHERE id = p_user_id);
END;
$$ LANGUAGE plpgsql;

-- RECHAZAR pago: orden sigue PENDING | sesión -> PENDING_PAYMENT_APPROVAL | ticket -> CLOSED
CREATE OR REPLACE FUNCTION bot_data.reject_payment(p_order_id INT)
RETURNS VOID AS $$
BEGIN
  UPDATE bot_data.chat_sessions s
     SET current_state = 'PENDING_PAYMENT_APPROVAL', last_interaction = NOW()
    FROM bot_data.orders o
   WHERE o.id = p_order_id AND s.user_id = o.user_id;

  UPDATE bot_data.tickets
     SET status = 'CLOSED',
         admin_notes = COALESCE(admin_notes, '') || ' | RECHAZADO ' || NOW()
   WHERE order_id = p_order_id AND ticket_type = 'PAYMENT_VALIDATION' AND status <> 'CLOSED';
END;
$$ LANGUAGE plpgsql;

-- RESOLVER reclamo: ticket -> CLOSED | sesión -> BOT_ACTIVE
CREATE OR REPLACE FUNCTION bot_data.resolve_claim(p_ticket_id INT)
RETURNS VOID AS $$
BEGIN
  UPDATE bot_data.tickets
     SET status = 'CLOSED',
         admin_notes = COALESCE(admin_notes, '') || ' | RESUELTO ' || NOW()
   WHERE id = p_ticket_id AND ticket_type = 'CLAIM';

  UPDATE bot_data.chat_sessions s
     SET current_state = 'BOT_ACTIVE', last_interaction = NOW()
    FROM bot_data.tickets t
   WHERE t.id = p_ticket_id AND s.user_id = t.user_id;
END;
$$ LANGUAGE plpgsql;
