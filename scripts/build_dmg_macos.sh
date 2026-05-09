#!/usr/bin/env bash
# Wrap the (ad-hoc signed) .app into a distributable DMG using
# hdiutil directly. We sidestep Tauri 1.x's bundle_dmg.sh because
# it has known instability on macOS Tahoe (compression / xattr edge
# cases that abort the build mid-bundle).
#
# This produces an unsigned (野良) DMG. End users will see a
# Gatekeeper warning on first launch; see
# docs/macos_unsigned_distribution.md for the bypass.
#
# Run order:
#     scripts/fetch_runtime_macos.sh            # stage runtime tree
#     scripts/build_sidecar.sh --onefile        # PyInstaller sidecar
#     npm run tauri:build --prefix frontend     # build the .app
#     scripts/post_bundle_macos.sh              # restore legal/
#     scripts/sign_adhoc_macos.sh               # ad-hoc sign
#     scripts/build_dmg_macos.sh                # this script

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="${APP_PATH:-$ROOT/frontend/src-tauri/target/release/bundle/macos/IMSLP Accompanist.app}"
OUT_DIR="${OUT_DIR:-$ROOT/dist}"

if [[ ! -d "$APP" ]]; then
  echo "ERROR: $APP not found. Run 'npm run tauri:build --prefix frontend' first." >&2
  exit 1
fi

VERSION="$(/usr/bin/python3 -c '
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]) / "frontend/src-tauri/tauri.conf.json"
print(json.loads(p.read_text())["package"]["version"])
' "$ROOT")"
DMG="$OUT_DIR/IMSLP-Accompanist-${VERSION}.dmg"

mkdir -p "$OUT_DIR"
rm -f "$DMG"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

# Drop the .app and an /Applications symlink into the stage dir so
# the user's drag-to-install workflow is the conventional one.
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"

echo "[dmg] creating $DMG"
hdiutil create \
    -volname "IMSLP Accompanist" \
    -srcfolder "$STAGE" \
    -ov \
    -format UDZO \
    "$DMG"

echo "[done]"
ls -lh "$DMG"
echo
echo "Distribute: $DMG"
echo "End-user install instructions: docs/macos_unsigned_distribution.md"
