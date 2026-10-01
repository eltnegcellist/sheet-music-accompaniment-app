#!/usr/bin/env bash
# Stage a relocatable homr interpreter and all weights at build time.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/frontend/src-tauri/resources/runtime/homr"
LEGAL="$ROOT/frontend/src-tauri/resources/legal/homr"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
case "$(uname -m)" in
  arm64)
    ARCH=aarch64
    SHA=53141f31b7cfb2bccf89c2a877827128657dbb8650db06a9a08c7886c28a45ed ;;
  x86_64)
    ARCH=x86_64
    SHA=d1143a947050fbbd17edc0d66ff3f7a63205c8364ef108bddfeece5f360096f8 ;;
  *) echo "Unsupported Mac architecture" >&2; exit 1 ;;
esac
URL="https://github.com/astral-sh/python-build-standalone/releases/download/20260929/cpython-3.11.16%2B20260929-$ARCH-apple-darwin-install_only_stripped.tar.gz"
curl --fail --location --retry 3 "$URL" -o "$WORK/python.tgz"
echo "$SHA  $WORK/python.tgz" | shasum -a 256 -c -
tar -xzf "$WORK/python.tgz" -C "$WORK"
rm -rf "$DEST"
mkdir -p "$DEST/bin" "$LEGAL"
# Avoid resource-walker symlink problems; keep every interpreter file local.
cp -RL "$WORK/python" "$DEST/python"
PY="$DEST/python/bin/python3.11"
"$PY" -I -m pip install --disable-pip-version-check --no-cache-dir 'homr==0.7.0'
"$PY" -I -B - <<'PY'
from homr.main import download_weights
from homr.title_detection import download_ocr_weights
download_weights(False, False, False)
download_weights(True, False, True)
download_ocr_weights()
PY
cat > "$DEST/bin/homr" <<'SH'
#!/bin/sh
set -eu
HOMR_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
unset PYTHONHOME PYTHONPATH DYLD_LIBRARY_PATH LD_LIBRARY_PATH
exec "$HOMR_ROOT/python/bin/python3.11" -I -B "$HOMR_ROOT/run_homr.py" "$@"
SH
chmod +x "$DEST/bin/homr"
cat > "$DEST/run_homr.py" <<'PY'
"""Relocatable entry point. CI can deny Python network connections."""
import os
import socket

if os.environ.get("HOMR_OFFLINE") == "1":
    def deny_network(*args, **kwargs):
        raise RuntimeError("Network access disabled for offline OMR verification")
    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    socket.create_connection = deny_network

from homr.main import main
main()
PY
curl --fail --location --retry 3 \
  https://raw.githubusercontent.com/liebharc/homr/v0.7.0/LICENSE \
  -o "$LEGAL/HOMR-LICENSE"
PY_LICENSE="$("$PY" -I -c 'import pathlib, sysconfig; print(pathlib.Path(sysconfig.get_path("stdlib")) / "LICENSE.txt")')"
cp "$PY_LICENSE" "$LEGAL/PYTHON-LICENSE"
"$PY" -I -m pip freeze > "$LEGAL/installed-packages.txt"
"$PY" -I -B - "$DEST" "$ARCH" "$SHA" <<'PY'
import hashlib
import importlib.metadata
import json
import pathlib
import sys
root = pathlib.Path(sys.argv[1])
models = sorted(root.rglob("*.onnx"))
assert len(models) >= 5, "Inference models were not fully staged"
manifest = {
    "homr": importlib.metadata.version("homr"),
    "python": sys.version,
    "architecture": sys.argv[2],
    "python_archive_sha256": sys.argv[3],
    "models": [
        {"path": str(p.relative_to(root)), "bytes": p.stat().st_size,
         "sha256": hashlib.file_digest(p.open("rb"), "sha256").hexdigest()}
        for p in models
    ],
}
(root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
PY
xattr -rc "$DEST" 2>/dev/null || true
echo "[homr] interpreter, CPU/CoreML weights and notices staged"
