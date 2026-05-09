#!/usr/bin/env bash
# Wrap the (signed/stapled) .app into a distributable DMG using
# hdiutil directly. We sidestep Tauri 1.x's bundle_dmg.sh because
# it has known instability on macOS Tahoe (compression / xattr edge
# cases that cause the bundling step to fail mid-build).
#
# Run order:
#     npm run tauri:build --prefix frontend     # builds the .app
#     scripts/post_bundle_macos.sh              # restores legal/
#     scripts/sign_and_notarize_macos.sh        # signs + notarizes .app
#     scripts/build_dmg_macos.sh                # this script
#
# Required env (only when signing/notarizing the DMG itself):
#     SIGN_IDENTITY    Developer ID Application identity
#     NOTARY_PROFILE   notarytool keychain profile
#
# Without these env vars the script produces an unsigned DMG, which
# is fine for sharing internally but will be Gatekeeper-rejected on
# end users' machines. For real distribution always sign + notarize.

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

# Drop the .app and an /Applications symlink into the stage dir.
# hdiutil's UDZO format compresses well and is the conventional
# DMG flavor for distributable Mac apps.
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"

echo "[dmg] creating $DMG"
hdiutil create \
    -volname "IMSLP Accompanist" \
    -srcfolder "$STAGE" \
    -ov \
    -format UDZO \
    "$DMG"

if [[ -n "${SIGN_IDENTITY:-}" ]]; then
  echo "[dmg] signing with $SIGN_IDENTITY"
  codesign --sign "$SIGN_IDENTITY" --timestamp "$DMG"

  if [[ -n "${NOTARY_PROFILE:-}" ]]; then
    echo "[dmg] notarizing"
    xcrun notarytool submit "$DMG" \
        --keychain-profile "$NOTARY_PROFILE" \
        --wait
    xcrun stapler staple "$DMG"
    xcrun stapler validate "$DMG"
  else
    echo "[dmg] NOTARY_PROFILE unset; DMG is signed but not notarized." >&2
  fi
else
  echo "[dmg] SIGN_IDENTITY unset; DMG is unsigned (internal-use only)." >&2
fi

echo "[done]"
ls -lh "$DMG"
