#!/usr/bin/env bash
# Restore the Adoptium legal/ tree into the bundled .app after
# `tauri build` completes.
#
# Background: fetch_runtime_macos.sh stages the JRE's legal/
# directory at frontend/src-tauri/legal-bundle/ (outside resources/)
# because tauri-build's resource walker hits EACCES on the symlinks
# under jre/legal/<module>/{LICENSE,ADDITIONAL_LICENSE_INFO,
# ASSEMBLY_EXCEPTION} on macOS Tahoe (com.apple.provenance is not
# removable via xattr -c). That keeps `tauri:dev` and `tauri:build`
# working but leaves the .app without the legal/ payload Adoptium's
# license requires for redistribution.
#
# Run this once after each `npm run tauri:build` to copy the staged
# legal/ tree into the canonical position inside the .app:
#
#     <App>/Contents/Resources/resources/runtime/jre/legal/
#
# Usage:
#     npm run tauri:build --prefix frontend
#     scripts/post_bundle_macos.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LEGAL_STAGE="$ROOT/frontend/src-tauri/legal-bundle"
APP="$ROOT/frontend/src-tauri/target/release/bundle/macos/IMSLP Accompanist.app"

if [[ ! -d "$APP" ]]; then
  echo "ERROR: .app not found at:" >&2
  echo "         $APP" >&2
  echo "       Did you run 'npm run tauri:build --prefix frontend' yet?" >&2
  exit 1
fi

if [[ ! -d "$LEGAL_STAGE" ]]; then
  echo "ERROR: legal-bundle/ not found at:" >&2
  echo "         $LEGAL_STAGE" >&2
  echo "       Run scripts/fetch_runtime_macos.sh first to stage it." >&2
  exit 1
fi

DEST="$APP/Contents/Resources/resources/runtime/jre/legal"
echo "[post-bundle] copying legal/ → $DEST"
rm -rf "$DEST"
cp -R "$LEGAL_STAGE" "$DEST"
echo "[post-bundle] legal/ entries:"
ls "$DEST" | sed 's/^/    /'
echo "[post-bundle] done"
