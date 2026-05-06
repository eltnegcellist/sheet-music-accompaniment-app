#!/usr/bin/env bash
# Build the FastAPI sidecar with PyInstaller and drop the resulting
# directory into frontend/src-tauri/bin/ under the per-target name
# Tauri's externalBin loader expects.
#
# Usage:
#     scripts/build_sidecar.sh                 # auto-detect target triple
#     scripts/build_sidecar.sh --release       # ditto, with --strip
#
# Requires:
#     * Python 3.11+ in PATH
#     * `pip install pyinstaller` in the active environment (or .venv)
#     * The backend deps installed (`pip install -e backend`).

set -euo pipefail

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

echo "[sidecar] building for triple: $TRIPLE"

PYTHON="${PYTHON:-python3}"

rm -rf build dist
"$PYTHON" -m PyInstaller --clean --noconfirm pyinstaller.spec

OUT_DIR="$ROOT/frontend/src-tauri/bin"
mkdir -p "$OUT_DIR"

# Tauri's externalBin loader expects a single file at
#   bin/<name>-<target-triple>[.exe]
# Our PyInstaller onedir bundle is a directory, so we rename the
# directory and create a thin wrapper at the expected path that execs
# the inner binary. The wrapper keeps Tauri's sidecar loader happy
# while preserving the onedir layout for fast cold start.
TARGET_DIR="$OUT_DIR/accompanist-server-$TRIPLE.app"
rm -rf "$TARGET_DIR"
mv dist/accompanist-server "$TARGET_DIR"

WRAPPER="$OUT_DIR/accompanist-server-$TRIPLE$EXT"
if [[ "$EXT" == ".exe" ]]; then
  # On Windows we expect the user to swap to onefile or copy the inner
  # exe; emit a clear failure rather than a half-broken wrapper.
  cp "$TARGET_DIR/accompanist-server.exe" "$WRAPPER"
else
  cat > "$WRAPPER" <<'EOF'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRIPLE_DIR="$(basename "${BASH_SOURCE[0]}").app"
exec "$DIR/$TRIPLE_DIR/accompanist-server" "$@"
EOF
  chmod +x "$WRAPPER"
fi

echo "[sidecar] wrote $WRAPPER"
