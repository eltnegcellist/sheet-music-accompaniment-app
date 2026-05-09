#!/usr/bin/env bash
# Sign, notarize, and staple the IMSLP Accompanist .app for macOS
# distribution outside the Mac App Store.
#
# This is the canonical post-`tauri:build` flow on a machine with a
# valid Apple Developer ID. The order matters: every nested Mach-O
# is signed leaf-up before the outer .app, then the whole bundle is
# zipped, submitted to notarytool, and stapled.
#
# Prerequisites:
#   1. Apple Developer Program membership ($99/yr).
#   2. "Developer ID Application: <Name> (TEAMID)" certificate
#      installed in the login keychain. Verify with:
#          security find-identity -v -p codesigning
#   3. notarytool credentials saved as a keychain profile (run once):
#          xcrun notarytool store-credentials "imslp-accompanist" \
#              --apple-id "<your-apple-id-email>" \
#              --team-id   "<TEAMID>" \
#              --password  "<app-specific-password>"
#      App-specific passwords are issued at https://appleid.apple.com.
#
# Required env:
#   SIGN_IDENTITY    e.g. "Developer ID Application: Foo Bar (ABCDE12345)"
#   NOTARY_PROFILE   keychain profile name (e.g. "imslp-accompanist")
#
# Optional:
#   APP_PATH         override .app path (default: locate from build)
#   SKIP_NOTARIZE    if set, sign + verify only (faster local iteration)
#
# Typical usage:
#     export SIGN_IDENTITY="Developer ID Application: Foo Bar (ABCDE12345)"
#     export NOTARY_PROFILE="imslp-accompanist"
#     npm run tauri:build --prefix frontend
#     scripts/post_bundle_macos.sh
#     scripts/sign_and_notarize_macos.sh
#     scripts/build_dmg_macos.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="${APP_PATH:-$ROOT/frontend/src-tauri/target/release/bundle/macos/IMSLP Accompanist.app}"
ENTITLEMENTS="$ROOT/frontend/src-tauri/entitlements.plist"

: "${SIGN_IDENTITY:?SIGN_IDENTITY env var is required (run: security find-identity -v -p codesigning)}"

if [[ ! -d "$APP" ]]; then
  echo "ERROR: $APP not found. Run 'npm run tauri:build --prefix frontend' first." >&2
  exit 1
fi
if [[ ! -f "$ENTITLEMENTS" ]]; then
  echo "ERROR: entitlements file missing at $ENTITLEMENTS" >&2
  exit 1
fi

echo "[sign] identity: $SIGN_IDENTITY"
echo "[sign] target:   $APP"

# 1. Sign every Mach-O inside the bundle, leaves first.
#
# Apple's notary service rejects an outer-only signature even with
# --deep when nested binaries lack the Hardened Runtime flag. We
# walk the tree manually and sign each Mach-O individually with the
# same entitlements + --options runtime.
#
# `file` is used to filter out scripts that happen to have the
# executable bit set (e.g. .py files inside PyInstaller's payload).
echo "[sign] signing nested Mach-O files (leaf-up)"
SIGNED_COUNT=0
while IFS= read -r -d '' f; do
  if file "$f" | grep -qE 'Mach-O|dynamically linked'; then
    codesign --force --options runtime --timestamp \
        --entitlements "$ENTITLEMENTS" \
        --sign "$SIGN_IDENTITY" "$f" 2>/dev/null
    SIGNED_COUNT=$((SIGNED_COUNT + 1))
  fi
done < <(find "$APP/Contents" -type f \( -name "*.dylib" -o -name "*.so" -o -perm -u=x \) -print0)
echo "[sign] signed $SIGNED_COUNT nested Mach-O files"

# 2. Sign the .app bundle itself last so its CodeResources reflects
#    the now-signed nested files.
echo "[sign] signing outer .app"
codesign --force --options runtime --timestamp \
    --entitlements "$ENTITLEMENTS" \
    --sign "$SIGN_IDENTITY" "$APP"

# 3. Verify before submitting to notarization. spctl is informational
#    only (it will report "rejected" pre-notarization, which is
#    expected); codesign --verify is the gate.
echo "[verify] codesign --verify --deep --strict"
codesign --verify --deep --strict --verbose=2 "$APP"
echo "[verify] spctl --assess (informational)"
spctl --assess --type execute --verbose=4 "$APP" || true

if [[ -n "${SKIP_NOTARIZE:-}" ]]; then
  echo "[done] SKIP_NOTARIZE set — exiting after signature verification."
  exit 0
fi

: "${NOTARY_PROFILE:?NOTARY_PROFILE env var is required for notarization (or set SKIP_NOTARIZE=1)}"

# 4. Notarize. notarytool waits synchronously and returns non-zero
#    on rejection. The submission UUID is logged so you can fetch
#    the full report later via 'xcrun notarytool log <uuid>'.
echo "[notarize] zipping and submitting (this may take several minutes)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
ZIP="$WORK/IMSLP-Accompanist.zip"
ditto -c -k --keepParent "$APP" "$ZIP"
xcrun notarytool submit "$ZIP" \
    --keychain-profile "$NOTARY_PROFILE" \
    --wait

# 5. Staple. Stapled apps satisfy Gatekeeper offline; without the
#    staple, first launch on the user's Mac requires online lookup.
echo "[staple] xcrun stapler staple"
xcrun stapler staple "$APP"
xcrun stapler validate "$APP"

echo "[done] $APP is signed, notarized, and stapled."
