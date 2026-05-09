#!/usr/bin/env bash
# Build the FastAPI sidecar with PyInstaller and drop the resulting
# binary into frontend/src-tauri/bin/ under the per-target name
# Tauri's externalBin loader expects.
#
# Usage:
#     scripts/build_sidecar.sh                  # onedir (fast cold start, dev)
#     scripts/build_sidecar.sh --onefile        # single binary (tauri build)
#
# Mode trade-off:
#   * onedir:  PyInstaller emits dist/accompanist-server/ ; we wrap it
#              with a thin shell script so Tauri externalBin sees a
#              single file. The .app/ companion directory must sit
#              next to the wrapper, which is fine for `tauri dev`
#              (the wrapper bakes in the absolute source path) but
#              breaks for `tauri build` (the .app/ isn't bundled).
#   * onefile: PyInstaller emits a self-extracting single binary.
#              Tauri externalBin ships it directly into the .app's
#              MacOS/ at build time. Cold start is +3-5s on first
#              launch only (extracted to /var/folders/.../_MEIxxxx
#              and cached).
#
# Requires:
#     * Python 3.11+ in PATH
#     * `pip install pyinstaller` in the active environment (or .venv)
#     * The backend deps installed (`pip install -e backend`).

set -euo pipefail

MODE="onedir"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --onefile|--release) MODE="onefile" ;;
    --onedir)            MODE="onedir" ;;
    -h|--help)
      sed -n '1,/^set -euo pipefail$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//; /^!/d'
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

# Resolve the Rust target triple so the binary lands at the path Tauri
# looks up via Command::new_sidecar("accompanist-server").
TRIPLE="$(rustc -vV 2>/dev/null | sed -n 's|host: ||p' || true)"
if [[ -z "${TRIPLE}" ]]; then
  case "$(uname -s)-$(uname -m)" in
    Darwin-arm64)  TRIPLE="aarch64-apple-darwin" ;;
    Darwin-x86_64) TRIPLE="x86_64-apple-darwin" ;;
    Linux-x86_64)  TRIPLE="x86_64-unknown-linux-gnu" ;;
    Linux-aarch64) TRIPLE="aarch64-unknown-linux-gnu" ;;
    *) echo "Unable to detect target triple. Install rustc or set TRIPLE." >&2; exit 1 ;;
  esac
fi

EXT=""
if [[ "$TRIPLE" == *windows* ]]; then EXT=".exe"; fi

echo "[sidecar] building ($MODE) for triple: $TRIPLE"

PYTHON="${PYTHON:-python3}"

rm -rf build dist
PYINSTALLER_MODE="$MODE" "$PYTHON" -m PyInstaller --clean --noconfirm pyinstaller.spec

OUT_DIR="$ROOT/frontend/src-tauri/bin"
mkdir -p "$OUT_DIR"
WRAPPER="$OUT_DIR/accompanist-server-$TRIPLE$EXT"

if [[ "$MODE" == "onefile" ]]; then
  # Drop any leftover onedir companion from a previous build so Tauri's
  # bundler doesn't accidentally pick it up alongside the new wrapper.
  rm -rf "$OUT_DIR/accompanist-server-$TRIPLE.app"
  cp "dist/accompanist-server$EXT" "$WRAPPER"
  chmod +x "$WRAPPER"
  echo "[sidecar] wrote $WRAPPER (onefile, $(du -h "$WRAPPER" | cut -f1))"
else
  TARGET_DIR="$OUT_DIR/accompanist-server-$TRIPLE.app"
  rm -rf "$TARGET_DIR"
  mv dist/accompanist-server "$TARGET_DIR"

  if [[ "$EXT" == ".exe" ]]; then
    cp "$TARGET_DIR/accompanist-server.exe" "$WRAPPER"
  else
    # Bake the absolute path of TARGET_DIR in so the wrapper still
    # resolves the bundle after Tauri relocates it to target/debug/.
    # Dev-only: the absolute path doesn't survive `tauri build` →
    # use --onefile for production.
    cat > "$WRAPPER" <<EOF
#!/usr/bin/env bash
exec "$TARGET_DIR/accompanist-server" "\$@"
EOF
    chmod +x "$WRAPPER"
  fi
  echo "[sidecar] wrote $WRAPPER (onedir wrapper → $TARGET_DIR)"
fi
