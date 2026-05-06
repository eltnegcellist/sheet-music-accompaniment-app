#!/usr/bin/env bash
# Sanity-check the Tauri sidecar/runtime layout before `tauri:build` ships
# it. Catches the packaging mistakes we've actually hit during this
# migration: missing Audiveris launcher, JRE that doesn't pass the
# `java -version` smoke test, sidecar binary that doesn't print READY.
#
# Run after build_sidecar.sh + fetch_runtime_<os>.sh, before tauri:build:
#
#     scripts/validate_bundle.sh
#
# Exits non-zero on the first missing piece so it can also be wired into
# release CI as a pre-bundle gate.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RES="$ROOT/frontend/src-tauri/resources"
BIN="$ROOT/frontend/src-tauri/bin"

fail() { echo "  ✗ $*" >&2; exit 1; }
ok()   { echo "  ✓ $*"; }

echo "[validate] sidecar binary"
shopt -s nullglob
SIDECARS=()
for cand in "$BIN"/accompanist-server-*-*; do
  # Skip the per-target onedir directory ($name.app); only the wrapper /
  # exe is what Tauri's externalBin loader spawns.
  [[ -f "$cand" ]] || continue
  SIDECARS+=("$cand")
done
shopt -u nullglob
[[ ${#SIDECARS[@]} -ge 1 ]] || fail "no sidecar in $BIN/. Run scripts/build_sidecar.sh."
for s in "${SIDECARS[@]}"; do
  [[ -x "$s" ]] || fail "$s is not executable"
  ok "$(basename "$s")"
done

echo "[validate] sidecar smoke (READY + /health)"
SIDECAR="${SIDECARS[0]}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
"$SIDECAR" --host 127.0.0.1 --port 0 --app-data "$TMP/data" \
    > "$TMP/out" 2> "$TMP/err" &
PID=$!

for _ in $(seq 1 60); do
  grep -q '^READY ' "$TMP/out" && break
  sleep 0.5
done

PORT="$(sed -n 's/.*"port": *\([0-9][0-9]*\).*/\1/p' "$TMP/out" | head -n1)"
if [[ -z "$PORT" ]]; then
  echo "stdout:"; cat "$TMP/out"
  echo "stderr:"; cat "$TMP/err"
  kill $PID 2>/dev/null || true
  fail "sidecar never printed a READY line"
fi
ok "READY line on port $PORT"

if curl --fail --silent --max-time 5 "http://127.0.0.1:$PORT/health" > "$TMP/health"; then
  ok "GET /health -> $(cat "$TMP/health")"
else
  kill $PID 2>/dev/null || true
  fail "GET /health did not return 200"
fi

kill $PID 2>/dev/null || true
wait $PID 2>/dev/null || true

echo "[validate] bundled runtime tree"
[[ -d "$RES/runtime/jre" ]] || fail "runtime/jre missing"
[[ -x "$RES/runtime/jre/bin/java" ]] || fail "runtime/jre/bin/java not executable"
ok "JRE present"

# `java -version` writes to stderr; capture both.
if "$RES/runtime/jre/bin/java" -version > "$TMP/java" 2>&1; then
  ok "java -version: $(head -n1 "$TMP/java")"
else
  cat "$TMP/java" >&2
  fail "java -version exited non-zero"
fi

# Audiveris ships either a Linux .deb-style bin/Audiveris or the
# Gradle installDist layout (lib/ + bin/<launcher>). Accept either.
AUD_LAUNCHER=""
for c in "$RES/runtime/audiveris/bin/Audiveris" \
         "$RES/runtime/audiveris/bin/Audiveris.bat" \
         "$RES/runtime/audiveris/bin/audiveris-app"; do
  [[ -e "$c" ]] && AUD_LAUNCHER="$c" && break
done
[[ -n "$AUD_LAUNCHER" ]] || fail "no Audiveris launcher under runtime/audiveris/bin/"
ok "Audiveris launcher: $(basename "$AUD_LAUNCHER")"

echo "[validate] Tesseract"
TESS=""
for c in "$RES/tesseract/tesseract" "$RES/tesseract/tesseract.exe"; do
  [[ -x "$c" ]] && TESS="$c" && break
done
[[ -n "$TESS" ]] || fail "no Tesseract binary under resources/tesseract/"
ok "Tesseract binary: $(basename "$TESS")"

[[ -d "$RES/runtime/tessdata" ]] || fail "runtime/tessdata missing"
TRAINED=("$RES/runtime/tessdata"/*.traineddata)
[[ ${#TRAINED[@]} -ge 1 ]] || fail "no .traineddata files in runtime/tessdata/"
ok "tessdata: ${#TRAINED[@]} language pack(s)"

echo "[validate] all checks passed"
