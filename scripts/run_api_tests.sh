#!/usr/bin/env bash
# Roda os testes HTTP (black-box) contra uma API local efêmera.
# Requer: DATABASE_URL (Postgres VAZIO e descartável), SECRET_KEY, REFRESH_SECRET_KEY,
#         MELHOR_ENVIO_TOKEN, MELHOR_ENVIO_USER_AGENT, STORE_ORIGIN_ZIP_CODE.
# Opcional: API_PORT (padrão: porta livre), HEALTH_TIMEOUT (s, padrão 60).
# Aplica `alembic upgrade head` (como produção), roda o seed (sem create_all),
# sobe uvicorn, roda pytest e sempre encerra o uvicorn.
set -euo pipefail

cd "$(dirname "$0")/.."

: "${DATABASE_URL:?DATABASE_URL (Postgres vazio e descartável) é obrigatório}"
# Compara o host exato (não substring): só bancos locais/efêmeros.
DB_HOST="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.urlsplit(sys.argv[1]).hostname or "")' "$DATABASE_URL")"
case "$DB_HOST" in
  localhost|127.0.0.1|postgres|db) ;;
  *) echo "Recusando: host do DATABASE_URL ('$DB_HOST') não é local/efêmero." >&2; exit 2 ;;
esac

# Sem Redis o rate limit fica desabilitado (evita 429 em logins sequenciais).
# Vazias (e não unset) para também sobrescrever valores vindos do .env.
export STORAGE_REDIS_URL="" RATE_LIMIT_REDIS_URL="" RATE_LIMIT_REDIS_REST_URL="" RATE_LIMIT_REDIS_REST_TOKEN=""

RUN=(python -m)
if command -v uv >/dev/null 2>&1; then RUN=(uv run python -m); fi

API_PORT="${API_PORT:-$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-60}"
LOG_FILE="$(mktemp)"
UVICORN_PID=""
FAKE_PID=""
FAKE_PORT="${BLING_FAKE_PORT:-$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')}"

cleanup() {
  status=$?
  if [ -n "$FAKE_PID" ]; then
    kill "$FAKE_PID" 2>/dev/null || true
    wait "$FAKE_PID" 2>/dev/null || true
  fi
  if [ -n "$UVICORN_PID" ]; then
    kill "$UVICORN_PID" 2>/dev/null || true
    wait "$UVICORN_PID" 2>/dev/null || true
  fi
  if [ "$status" -ne 0 ]; then
    echo "----- uvicorn log -----" >&2
    cat "$LOG_FILE" >&2 || true
  fi
  rm -f "$LOG_FILE" "$LOG_FILE.fake"
  exit "$status"
}
trap cleanup EXIT

# Bling simulado (nunca o Bling real) + variáveis fictícias da integração.
export TENANT_ID="test-tenant" FRONT_URL="https://front.test"
export BLING_CLIENT_ID="test-client-id" BLING_CLIENT_SECRET="test-client-secret"
export BLING_STATE_SIGNING_KEY="test-state-signing-key-not-secret"
BLING_TOKEN_ENCRYPTION_KEY="$(python3 -c 'import base64; print(base64.urlsafe_b64encode(b"0123456789abcdef0123456789abcdef").decode())')"
export BLING_TOKEN_ENCRYPTION_KEY
export BLING_FAKE_URL="http://127.0.0.1:${FAKE_PORT}"
export BLING_AUTH_BASE_URL="${BLING_FAKE_URL}/Api/v3" BLING_API_BASE_URL="${BLING_FAKE_URL}/Api/v3"

"${RUN[@]}" alembic upgrade head
"${RUN[@]}" scripts.seed

"${RUN[@]}" uvicorn tests.fakes.bling_fake:app --host 127.0.0.1 --port "$FAKE_PORT" >"$LOG_FILE.fake" 2>&1 &
FAKE_PID=$!

"${RUN[@]}" uvicorn src.main:app --host 127.0.0.1 --port "$API_PORT" >"$LOG_FILE" 2>&1 &
UVICORN_PID=$!

export BASE_URL="http://127.0.0.1:${API_PORT}"
for _ in $(seq 1 "$HEALTH_TIMEOUT"); do
  if ! kill -0 "$UVICORN_PID" 2>/dev/null; then echo "uvicorn encerrou antes do /health" >&2; exit 1; fi
  if curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS "$BASE_URL/health" >/dev/null || { echo "timeout aguardando /health" >&2; exit 1; }
for _ in $(seq 1 "$HEALTH_TIMEOUT"); do
  curl -fsS "$BLING_FAKE_URL/health" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS "$BLING_FAKE_URL/health" >/dev/null || { echo "timeout aguardando o Bling simulado" >&2; exit 1; }

"${RUN[@]}" pytest -q \
  tests/admin/test_auth.py tests/admin/test_bling_pending.py tests/admin/test_dashboard.py tests/admin/test_expressions.py tests/admin/test_moderation.py tests/admin/test_orders.py \
  tests/admin/test_presentation.py tests/admin/test_products.py tests/admin/test_visibility.py \
  tests/catalog/test_catalog.py tests/catalog/test_product_filters.py \
  tests/catalog/test_product_main_image.py \
  tests/integrations/test_bling_catalog_sync.py tests/integrations/test_bling_catalog_sync_api.py \
  tests/integrations/test_bling_connection.py \
  tests/identity/test_addresses.py tests/identity/test_auth.py tests/identity/test_users.py \
  tests/operations/test_shipping.py \
  tests/sales/test_cart.py tests/sales/test_checkout.py tests/sales/test_orders.py \
  "$@"
