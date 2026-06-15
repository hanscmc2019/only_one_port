"""Endpoints del Monitor de Ventas del bot de WhatsApp.

Leen/operan sobre el schema bot_data (en el mismo Postgres del e-commerce) con
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
FROM bot_data.users u
LEFT JOIN bot_data.chat_sessions s ON s.user_id = u.id
LEFT JOIN LATERAL (
    SELECT * FROM bot_data.orders o2
    WHERE o2.user_id = u.id ORDER BY o2.created_at DESC LIMIT 1
) o ON TRUE
LEFT JOIN LATERAL (
    SELECT * FROM bot_data.tickets t2
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
FROM bot_data.orders o
JOIN bot_data.users u ON u.id = o.user_id
LEFT JOIN LATERAL (
    SELECT * FROM bot_data.tickets t2
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
            "SELECT sender_type, content, created_at FROM bot_data.chat_messages "
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

        rows = _run("SELECT phone FROM bot_data.users WHERE id = %s", [user_id])
        if not rows:
            return Response({'error': 'usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)
        phone = rows[0]['phone']

        try:
            _evolution_send_text(phone, text)
        except Exception as e:
            return Response({'error': f'Evolution no pudo enviar el mensaje: {e}'},
                            status=status.HTTP_502_BAD_GATEWAY)

        # Solo se registra si Evolution aceptó el envío (el chat refleja lo realmente enviado).
        _run("INSERT INTO bot_data.chat_messages (user_id, sender_type, content) "
             "VALUES (%s, 'ADMIN', %s)", [user_id, text], fetch=False)
        return Response({'ok': True})


class ApprovePaymentView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, order_id):
        _run("SELECT bot_data.approve_payment(%s)", [order_id], fetch=False)
        return Response({'ok': True})


class RejectPaymentView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, order_id):
        _run("SELECT bot_data.reject_payment(%s)", [order_id], fetch=False)
        return Response({'ok': True})


class ResolveClaimView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, ticket_id):
        _run("SELECT bot_data.resolve_claim(%s)", [ticket_id], fetch=False)
        return Response({'ok': True})


_EXT_BY_MIME = {'image/jpeg': 'jpg', 'image/jpg': 'jpg', 'image/png': 'png', 'image/webp': 'webp'}


class PaymentProofIngestView(APIView):
    """Ingesta interna del comprobante (la llama n8n). Sin JWT: token compartido."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        if request.headers.get('X-Bot-Token') != settings.BOT_INTERNAL_TOKEN:
            return Response({'error': 'forbidden'}, status=status.HTTP_403_FORBIDDEN)

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
        _run("UPDATE bot_data.orders SET payment_proof_url = %s WHERE id = %s",
             [url, order_id], fetch=False)
        return Response({'ok': True, 'payment_proof_url': url})
