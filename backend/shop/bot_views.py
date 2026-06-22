"""Endpoints del Monitor de Ventas del bot de WhatsApp.

Leen/operan sobre el schema tienda (en el mismo Postgres del e-commerce) con
SQL crudo, reutilizando las queries y funciones del panel FastAPI original.
Acceso: IsAdminRole (ADMIN/SUPERADMIN) salvo la ingesta de comprobantes, que la
llama n8n con un token interno.
"""
import base64
import json
import os
import urllib.request

from django.conf import settings
from django.db import connection
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

from .views import IsAdminRole


def _dictfetchall(cursor):
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _run(sql, params=None, fetch=True):
    with connection.cursor() as cur:
        cur.execute(sql, params or [])
        return _dictfetchall(cur) if fetch else None


# ── Columna izquierda: clientes con estado + última orden + ticket abierto ──
CLIENTS_SQL = """
SELECT u.id                                    AS user_id,
       u.phone,
       u.name,
       COALESCE(s.current_state, 'BOT_ACTIVE') AS current_state,
       s.last_interaction,
       o.id            AS order_id,
       o.total_amount,
       o.status        AS order_status,
       o.payment_operation_code,
       t.id            AS ticket_id,
       t.ticket_type,
       t.status        AS ticket_status,
       t.admin_notes
FROM tienda.users u
LEFT JOIN tienda.chat_sessions s ON s.user_id = u.id
LEFT JOIN LATERAL (
    SELECT * FROM tienda.orders o2
    WHERE o2.user_id = u.id ORDER BY o2.created_at DESC LIMIT 1
) o ON TRUE
LEFT JOIN LATERAL (
    SELECT * FROM tienda.tickets t2
    WHERE t2.user_id = u.id AND t2.status <> 'CLOSED'
    ORDER BY t2.created_at DESC LIMIT 1
) t ON TRUE
ORDER BY (t.id IS NOT NULL) DESC, s.last_interaction DESC NULLS LAST;
"""

# ── Columna central: órdenes (con su ticket abierto, si lo hay) ──
ORDERS_SQL = """
SELECT o.id,
       o.user_id,
       o.total_amount,
       o.status,
       o.payment_operation_code,
       o.items,
       o.payment_proof_url,
       o.created_at,
       u.phone,
       u.name,
       t.id          AS ticket_id,
       t.ticket_type,
       t.status      AS ticket_status
FROM tienda.orders o
JOIN tienda.users u ON u.id = o.user_id
LEFT JOIN LATERAL (
    SELECT * FROM tienda.tickets t2
    WHERE t2.order_id = o.id AND t2.status <> 'CLOSED'
    ORDER BY t2.created_at DESC LIMIT 1
) t ON TRUE
{where}
ORDER BY o.created_at DESC;
"""


class ClientsView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        return Response(_run(CLIENTS_SQL))


class OrdersView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        user_id = request.query_params.get('user_id')
        if user_id and str(user_id).isdigit():
            sql = ORDERS_SQL.format(where="WHERE o.user_id = %s")
            return Response(_run(sql, [user_id]))
        return Response(_run(ORDERS_SQL.format(where="")))


class ChatView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        user_id = request.query_params.get('user_id')
        if not (user_id and str(user_id).isdigit()):
            return Response({'error': 'user_id requerido'}, status=status.HTTP_400_BAD_REQUEST)
        rows = _run(
            "SELECT sender_type, content, created_at FROM tienda.chat_messages "
            "WHERE user_id = %s ORDER BY id",
            [user_id],
        )
        return Response(rows)


def _evolution_send_text(number, text):
    """Envía un texto por Evolution API a un número de WhatsApp."""
    url = f"{settings.EVOLUTION_API_URL}/message/sendText/{settings.EVOLUTION_INSTANCE}"
    payload = json.dumps({"number": number, "text": text}).encode('utf-8')
    req = urllib.request.Request(url, data=payload, method='POST', headers={
        'Content-Type': 'application/json',
        'apikey': settings.EVOLUTION_API_KEY,
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status


class SendMessageView(APIView):
    """El admin envía un mensaje de texto al usuario por WhatsApp y lo registra."""
    permission_classes = [IsAdminRole]

    def post(self, request):
        user_id = request.data.get('user_id')
        text = (request.data.get('text') or '').strip()
        if not user_id or not text:
            return Response({'error': 'user_id y text requeridos'}, status=status.HTTP_400_BAD_REQUEST)

        rows = _run("SELECT phone FROM tienda.users WHERE id = %s", [user_id])
        if not rows:
            return Response({'error': 'usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)
        phone = rows[0]['phone']

        try:
            _evolution_send_text(phone, text)
        except Exception as e:
            return Response({'error': f'Evolution no pudo enviar el mensaje: {e}'},
                            status=status.HTTP_502_BAD_GATEWAY)

        # Solo se registra si Evolution aceptó el envío (el chat refleja lo realmente enviado).
        _run("INSERT INTO tienda.chat_messages (user_id, sender_type, content) "
             "VALUES (%s, 'ADMIN', %s)", [user_id, text], fetch=False)
        return Response({'ok': True})


class ApprovePaymentView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, order_id):
        _run("SELECT tienda.approve_payment(%s)", [order_id], fetch=False)
        return Response({'ok': True})


class ManualSaleView(APIView):
    """Venta manual del admin (página Ventas): crea una orden PAID y descuenta stock.

    El cliente (nombre/número) se guarda suelto en la orden (no se enlaza a
    tienda.users; user_id queda NULL). Reusa tienda.approve_payment para marcar
    PAID e insertar un movimiento VENTA por ítem (el trigger baja el stock).
    """
    permission_classes = [IsAdminRole]

    def post(self, request):
        data = request.data
        customer_name = (data.get('customer_name') or '').strip() or None
        customer_phone = (data.get('customer_phone') or '').strip() or None
        items_in = data.get('items') or []
        if not items_in:
            return Response({'error': 'La venta no tiene productos.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Normaliza ítems y agrega la cantidad pedida por (producto, variante).
        norm = []          # ítems con la forma que espera approve_payment
        needed = {}        # (id_product, id_variant|None) -> cantidad total pedida
        for it in items_in:
            pid = it.get('id_product')
            qty = it.get('qty')
            try:
                pid = int(pid); qty = int(qty); price = float(it.get('price'))
            except (TypeError, ValueError):
                return Response({'error': 'Ítem inválido (producto/cantidad/precio).'},
                                status=status.HTTP_400_BAD_REQUEST)
            if qty <= 0:
                return Response({'error': 'La cantidad debe ser mayor a 0.'},
                                status=status.HTTP_400_BAD_REQUEST)
            size = (it.get('size') or '').strip() or None
            color = (it.get('color') or '').strip() or None

            # Resuelve la variante por talla/color (si el producto las maneja).
            variant_id = None
            if size is not None or color is not None:
                vrows = _run(
                    "SELECT id, stock FROM tienda.product_variant "
                    "WHERE id_product = %s "
                    "AND size IS NOT DISTINCT FROM %s AND color IS NOT DISTINCT FROM %s",
                    [pid, size, color])
                if not vrows:
                    return Response({'error': f'No existe la variante {size or ""}/{color or ""} del producto.'},
                                    status=status.HTTP_400_BAD_REQUEST)
                variant_id = vrows[0]['id']

            key = (pid, variant_id)
            needed[key] = needed.get(key, 0) + qty
            prow = _run("SELECT product_name FROM tienda.product WHERE id = %s", [pid])
            if not prow:
                return Response({'error': f'Producto {pid} no encontrado.'},
                                status=status.HTTP_400_BAD_REQUEST)
            item = {'sku': f'PROD-{pid}', 'name': prow[0]['product_name'],
                    'qty': qty, 'price': price}
            if size is not None:
                item['size'] = size
            if color is not None:
                item['color'] = color
            norm.append(item)

        # Valida stock disponible por (producto, variante).
        for (pid, variant_id), qty in needed.items():
            if variant_id is not None:
                srow = _run("SELECT stock FROM tienda.product_variant WHERE id = %s", [variant_id])
            else:
                srow = _run("SELECT stock FROM tienda.product WHERE id = %s", [pid])
            available = (srow[0]['stock'] if srow else 0) or 0
            if qty > available:
                return Response(
                    {'error': f'Stock insuficiente (disponible {available}, pedido {qty}).'},
                    status=status.HTTP_400_BAD_REQUEST)

        total = sum(i['qty'] * i['price'] for i in norm)

        # Crea la orden PENDING y la aprueba (PAID + movimientos VENTA → baja stock).
        rows = _run(
            "INSERT INTO tienda.orders "
            "(user_id, customer_name, customer_phone, items, total_amount, status) "
            "VALUES (NULL, %s, %s, %s::jsonb, %s, 'PENDING') RETURNING id",
            [customer_name, customer_phone, json.dumps(norm), total])
        order_id = rows[0]['id']
        _run("SELECT tienda.approve_payment(%s)", [order_id], fetch=False)
        return Response({'ok': True, 'order_id': order_id}, status=status.HTTP_201_CREATED)


class RecentSalesView(APIView):
    """Últimas ventas (órdenes PAID) para la página de Ventas, agrupadas por orden.

    Incluye ventas del bot y manuales. Cada orden trae sus ítems (producto,
    talla/color, cantidad, subtotal). Filtros opcionales `?id_category=&id_product=`
    que recortan a los ítems que coinciden (la orden se omite si no le queda ninguno).
    """
    permission_classes = [IsAdminRole]

    def get(self, request):
        q = request.query_params
        id_product = int(q['id_product']) if (q.get('id_product') or '').isdigit() else None
        id_category = int(q['id_category']) if (q.get('id_category') or '').isdigit() else None

        # Mapa producto -> categoría (para filtrar por categoría sobre los items JSONB).
        prod_cat = {r['id']: r['id_category']
                    for r in _run("SELECT id, id_category FROM tienda.product")}

        orders = _run(
            "SELECT o.id, o.created_at, o.items, o.customer_name, "
            "       u.name AS user_name, u.phone AS user_phone "
            "FROM tienda.orders o "
            "LEFT JOIN tienda.users u ON u.id = o.user_id "
            "WHERE o.status = 'PAID' "
            "ORDER BY o.created_at DESC LIMIT 100")

        out = []
        for o in orders:
            items = o['items']
            if isinstance(items, str):
                items = json.loads(items or '[]')
            rows = []
            for it in (items or []):
                digits = ''.join(ch for ch in (it.get('sku') or '') if ch.isdigit())
                pid = int(digits) if digits else None
                if id_product and pid != id_product:
                    continue
                if id_category and prod_cat.get(pid) != id_category:
                    continue
                qty = it.get('qty') or 0
                price = float(it.get('price') or 0)
                rows.append({
                    'name': it.get('name') or (f'#{pid}' if pid else ''),
                    'size': it.get('size'),
                    'color': it.get('color'),
                    'qty': qty,
                    'price': price,
                    'subtotal': qty * price,
                })
            if not rows:
                continue
            out.append({
                'order_id': o['id'],
                'customer': o['customer_name'] or o['user_name'] or o['user_phone'] or '—',
                'created_at': o['created_at'],
                'items': rows,
            })
        return Response(out)


class RejectPaymentView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, order_id):
        _run("SELECT tienda.reject_payment(%s)", [order_id], fetch=False)
        return Response({'ok': True})


class ResolveClaimView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, ticket_id):
        _run("SELECT tienda.resolve_claim(%s)", [ticket_id], fetch=False)
        return Response({'ok': True})


_EXT_BY_MIME = {'image/jpeg': 'jpg', 'image/jpg': 'jpg', 'image/png': 'png', 'image/webp': 'webp'}


class PaymentProofIngestView(APIView):
    """Ingesta interna del comprobante (la llama n8n por la red interna).

    Sin JWT ni token: solo es accesible desde dentro de la red del stack
    (n8n → backend:8000). nginx bloquea esta ruta desde el exterior.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        order_id = request.data.get('order_id')
        b64 = request.data.get('base64')
        mimetype = request.data.get('mimetype', 'image/jpeg')
        if not order_id or not b64:
            return Response({'error': 'order_id y base64 requeridos'}, status=status.HTTP_400_BAD_REQUEST)

        if ',' in b64:  # tolera prefijo data:...;base64,
            b64 = b64.split(',', 1)[1]
        try:
            data = base64.b64decode(b64)
        except Exception:
            return Response({'error': 'base64 inválido'}, status=status.HTTP_400_BAD_REQUEST)

        ext = _EXT_BY_MIME.get(mimetype, 'jpg')
        folder = os.path.join(settings.MEDIA_ROOT, 'comprobantes')
        os.makedirs(folder, exist_ok=True)
        filename = f'{order_id}.{ext}'
        with open(os.path.join(folder, filename), 'wb') as f:
            f.write(data)

        url = f'/media/comprobantes/{filename}'
        _run("UPDATE tienda.orders SET payment_proof_url = %s WHERE id = %s",
             [url, order_id], fetch=False)
        return Response({'ok': True, 'payment_proof_url': url})
