#!/bin/sh
# Entrypoint del contenedor n8n (corre como usuario `node`).
# Siembra el workflow del bot + sus credenciales la PRIMERA vez (schema n8n vacío,
# p. ej. tras borrar los volúmenes), y luego arranca n8n. Es idempotente: si el
# workflow ya existe, NO reimporta (así no pisa ediciones hechas en la UI).
set -e

WF_ID='GlC4IjxnLdfRBj3H'

# Encadenado con && para que un fallo corte la secuencia. (No se puede confiar en
# `set -e` aquí: queda desactivado dentro de una función usada como condición.)
seed() {
  echo "[seed] Sembrando workflow y credenciales desde el .env..."
  node /opt/n8n-seed/seed/gen.js \
    && n8n import:credentials --input=/tmp/creds.json \
    && n8n import:workflow    --input=/tmp/wf.json \
    && n8n update:workflow --id="$WF_ID" --active=true
}

# Crea el owner de n8n desde el .env para no rellenar el formulario de setup a mano.
# n8n 2.x ya no permite desactivar el login; lo más cercano es pre-crear el owner.
# Corre en segundo plano porque la API necesita el servidor HTTP ya escuchando.
# Es idempotente: solo crea el owner si todavía no existe (showSetupOnFirstLoad).
N8N_URL='http://127.0.0.1:5678'
provision_owner() {
  [ -n "$N8N_OWNER_EMAIL" ] && [ -n "$N8N_OWNER_PASSWORD" ] || return 0
  i=0
  while [ "$i" -lt 90 ]; do
    wget -qO- "$N8N_URL/rest/settings" >/dev/null 2>&1 && break
    i=$((i + 1)); sleep 2
  done
  case "$(wget -qO- "$N8N_URL/rest/settings" 2>/dev/null)" in
    *'"showSetupOnFirstLoad":true'*) ;;
    *) echo "[seed] owner ya existe; no se recrea."; return 0 ;;
  esac
  # Capturamos la respuesta para mostrar el motivo exacto si n8n la rechaza
  # (p. ej. la contraseña requiere min 8, 1 mayúscula y 1 número).
  resp=$(wget -qO- --header='Content-Type: application/json' \
       --post-data="{\"email\":\"$N8N_OWNER_EMAIL\",\"firstName\":\"Admin\",\"lastName\":\"Bot\",\"password\":\"$N8N_OWNER_PASSWORD\"}" \
       "$N8N_URL/rest/owner/setup" 2>/dev/null)
  case "$resp" in
    *'"isOwner":true'*) echo "[seed] owner creado: $N8N_OWNER_EMAIL" ;;
    *) echo "[seed] AVISO: no se pudo crear el owner (revisa N8N_OWNER_* en el .env): ${resp:-sin respuesta}" ;;
  esac
}

if n8n list:workflow 2>/dev/null | grep -q "$WF_ID"; then
  echo "[seed] El workflow $WF_ID ya existe; no se reimporta."
elif seed; then
  echo "[seed] Listo. Workflow $WF_ID importado y activado."
  rm -f /tmp/wf.json /tmp/creds.json
else
  # No abortar el arranque por un fallo de siembra (p. ej. OPENROUTER_API_KEY sin
  # configurar): n8n levanta igual y la siembra se reintenta en el próximo arranque.
  echo "[seed] AVISO: la siembra falló (¿faltan variables en el .env?). n8n arranca sin el flow; corrige el .env y reinicia."
  rm -f /tmp/wf.json /tmp/creds.json 2>/dev/null || true
fi

provision_owner &

exec n8n start
