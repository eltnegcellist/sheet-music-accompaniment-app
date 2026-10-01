#!/usr/bin/env bash
set -euo pipefail
OUT="${VERIFY_OUTPUT:-verification-results}"
mkdir -p "$OUT"
python scripts/backend_replay_server.py backend/tests/fixtures/hybrid_p08 "$OUT" > "$OUT/backend.log" 2>&1 &
BACKEND_PID=$!
python -m http.server 5173 --bind 127.0.0.1 --directory "${VERIFY_UI_DIR:-frontend/dist}" > "$OUT/ui.log" 2>&1 &
UI_PID=$!
trap 'kill "$BACKEND_PID" "$UI_PID" 2>/dev/null || true' EXIT
for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:18765/health >/dev/null && curl -fsS http://127.0.0.1:5173/ >/dev/null; then break; fi
  sleep 0.5
done
curl -fsS http://127.0.0.1:18765/health
python scripts/verify_replay_api.py "$OUT"
node scripts/verify_browser_audio.cjs "$OUT"
