#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
ENV_FILE="$ROOT/.omr-server.env"
COMPOSE_FILE="$ROOT/docker-compose.server.yml"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required: https://docs.docker.com/get-docker/" >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required (docker compose)." >&2
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  if command -v openssl >/dev/null 2>&1; then
    TOKEN="$(openssl rand -hex 24)"
  elif command -v python3 >/dev/null 2>&1; then
    TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
  else
    echo "Need openssl or python3 to generate API_TOKEN." >&2
    exit 1
  fi
  {
    echo "API_TOKEN=$TOKEN"
    echo "OMR_BIND=0.0.0.0"
    echo "OMR_PORT=8000"
  } > "$ENV_FILE"
  chmod 600 "$ENV_FILE" 2>/dev/null || true
else
  TOKEN="$(sed -n 's/^API_TOKEN=//p' "$ENV_FILE" | head -n1)"
fi

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build

PORT="$(sed -n 's/^OMR_PORT=//p' "$ENV_FILE" | head -n1)"
PORT="${PORT:-8000}"

IP=""
if command -v hostname >/dev/null 2>&1; then
  IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
fi
if [ -z "$IP" ] && command -v ipconfig >/dev/null 2>&1; then
  IP="$(ipconfig getifaddr en0 2>/dev/null || true)"
fi

echo ""
echo "IMSLP Accompanist OMR server is starting."
echo "Android settings:"
if [ -n "$IP" ]; then
  echo "  Server URL: http://$IP:$PORT"
else
  echo "  Server URL: http://<this-computer-LAN-IP>:$PORT"
fi
echo "  API token: $TOKEN"
echo ""
echo "Connection test:"
echo "  curl http://127.0.0.1:$PORT/health"
echo ""
echo "For Internet access, put the server behind HTTPS. Do not expose plain HTTP to the Internet."
