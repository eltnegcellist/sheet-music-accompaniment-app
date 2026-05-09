#!/usr/bin/env bash
# Ad-hoc sign every Mach-O inside the .app for unsigned (野良)
# distribution. We do NOT use Hardened Runtime or entitlements —
# those are notarization prerequisites, and notarization requires
# an Apple Developer account. Without Hardened Runtime the JVM and
# bundled dylibs run without the JIT/library-validation restrictions
# that would otherwise demand entitlements.
#
# Why ad-hoc sign at all?
#
# 1. install_name_tool (used by bundle_macho_macos.sh to relink the
#    Poppler tree) invalidates whatever signature each binary had.
#    macOS Sonoma+ refuses to load a Mach-O whose code signature
#    doesn't match its current contents — even an ad-hoc signature
#    is enough to satisfy that check.
#
# 2. Tauri produces an unsigned .app by default (signingIdentity is
#    null). Ad-hoc signing the outer bundle ensures every nested
#    file's hash is recorded in CodeResources, so future tampering
#    is at least detectable by `codesign --verify`.
#
# This script does not eliminate the Gatekeeper warning end users
# see on first launch — that requires notarization. See
# docs/macos_unsigned_distribution.md for the user-side bypass.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="${APP_PATH:-$ROOT/frontend/src-tauri/target/release/bundle/macos/IMSLP Accompanist.app}"

if [[ ! -d "$APP" ]]; then
  echo "ERROR: $APP not found. Run 'npm run tauri:build --prefix frontend' first." >&2
  exit 1
fi

echo "[adhoc] target: $APP"

# Sign every nested Mach-O leaf-up. The order matters: signing the
# outer bundle hashes the contents of every nested file, so any
# nested file modified after the outer signature invalidates it.
echo "[adhoc] signing nested Mach-O files"
SIGNED=0
while IFS= read -r -d '' f; do
  if file "$f" | grep -qE 'Mach-O|dynamically linked'; then
    codesign --force --sign - --timestamp=none "$f" 2>/dev/null
    SIGNED=$((SIGNED + 1))
  fi
done < <(find "$APP/Contents" -type f \( -name "*.dylib" -o -name "*.so" -o -perm -u=x \) -print0)
echo "[adhoc] signed $SIGNED nested Mach-O files"

echo "[adhoc] signing outer .app"
codesign --force --sign - --timestamp=none "$APP"

echo "[verify] codesign --verify --deep --strict"
codesign --verify --deep --strict --verbose=2 "$APP"

echo "[done] $APP is ad-hoc signed."
echo
echo "Next: scripts/build_dmg_macos.sh to package into a DMG."
echo "End-user install instructions: docs/macos_unsigned_distribution.md"
