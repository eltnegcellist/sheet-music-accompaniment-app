#!/usr/bin/env bash
# Assemble the bundled runtime tree for macOS (arm64 + x64). Run on the
# target Mac you intend to ship from — Audiveris is built from source
# because the upstream project does not publish a macOS tarball.
#
# Output layout (matches frontend/src-tauri/src/main.rs env wiring):
#
#   frontend/src-tauri/resources/
#     runtime/
#       jre/                     <- Temurin 25 JRE (jlink-trimmed)
#       audiveris/               <- Audiveris install (built locally)
#       tessdata/                <- Tesseract language packs
#     tesseract/
#       tesseract                <- Tesseract binary (Homebrew copy)
#
# Prerequisites:
#     brew install tesseract gradle git
#
# Usage:
#     scripts/fetch_runtime_macos.sh                # auto-detect arch
#     ARCH=aarch64 scripts/fetch_runtime_macos.sh   # cross-arch override

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RES="$ROOT/frontend/src-tauri/resources"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$RES/runtime" "$RES/tesseract"

ARCH="${ARCH:-$(uname -m)}"
case "$ARCH" in
  arm64|aarch64) JRE_ARCH="aarch64" ;;
  x86_64)        JRE_ARCH="x64" ;;
  *) echo "Unsupported macOS arch: $ARCH" >&2; exit 1 ;;
esac

# Audiveris 5.10.2's build.gradle pins sourceCompatibility to Java 25,
# so we must ship a JDK 25 toolchain. Use the Adoptium API "latest GA"
# endpoint so we don't have to chase point releases.
JRE_FEATURE="${JRE_FEATURE:-25}"
case "$JRE_ARCH" in
  aarch64) ADOPTIUM_ARCH="aarch64" ;;
  x64)     ADOPTIUM_ARCH="x64" ;;
esac
JRE_URL="https://api.adoptium.net/v3/binary/latest/${JRE_FEATURE}/ga/mac/${ADOPTIUM_ARCH}/jdk/hotspot/normal/eclipse"
AUDIVERIS_REF="${AUDIVERIS_REF:-5.10.2}"

# ---------------------------------------------------------------------------
# 1. Trimmed JRE via jlink. macOS Temurin tarball has a Contents/Home/
#    layout from the .pkg, so we strip the wrapper before invoking jlink.
# ---------------------------------------------------------------------------
echo "[runtime] fetching latest Temurin JDK $JRE_FEATURE GA ($JRE_ARCH)"
curl -fsSL "$JRE_URL" -o "$WORK/jdk.tgz"
mkdir -p "$WORK/jdk-extract"
tar -xzf "$WORK/jdk.tgz" -C "$WORK/jdk-extract"
JDK_HOME="$(find "$WORK/jdk-extract" -type d -name "Home" -path "*Contents*" | head -n1)"
if [[ -z "$JDK_HOME" ]]; then
  JDK_HOME="$(find "$WORK/jdk-extract" -maxdepth 3 -type d -name "jdk-*" | head -n1)"
fi
if [[ -z "$JDK_HOME" || ! -x "$JDK_HOME/bin/jlink" ]]; then
  echo "ERROR: could not locate JDK home under $WORK/jdk-extract" >&2
  exit 1
fi

echo "[runtime] running jlink (JDK_HOME=$JDK_HOME)"
rm -rf "$RES/runtime/jre"
"$JDK_HOME/bin/jlink" \
    --module-path "$JDK_HOME/jmods" \
    --add-modules java.base,java.desktop,java.logging,java.sql,java.xml,jdk.unsupported,jdk.crypto.ec,jdk.localedata \
    --include-locales=en,ja \
    --no-header-files \
    --no-man-pages \
    --strip-debug \
    --compress=zip-6 \
    --output "$RES/runtime/jre"

# ---------------------------------------------------------------------------
# 2. Audiveris from source. The upstream Gradle build produces an install
#    layout under build/install/audiveris-app/ that mirrors the Linux .deb.
# ---------------------------------------------------------------------------
echo "[runtime] cloning + building Audiveris @ $AUDIVERIS_REF"
git clone --depth 1 --branch "$AUDIVERIS_REF" \
    https://github.com/Audiveris/audiveris.git "$WORK/audiveris"

(
  cd "$WORK/audiveris"
  # Install layout includes the launcher under bin/Audiveris and all jars
  # under lib/. installDist is faster than build because it skips tests.
  JAVA_HOME="$JDK_HOME" ./gradlew --no-daemon installDist
)

INSTALL_DIR="$(find "$WORK/audiveris" -type d -path "*build/install/*" -maxdepth 5 | head -n1)"
if [[ -z "$INSTALL_DIR" || ! -x "$INSTALL_DIR/bin/Audiveris" ]]; then
  echo "ERROR: Audiveris install layout not found after gradlew installDist." >&2
  exit 1
fi
rm -rf "$RES/runtime/audiveris"
cp -R "$INSTALL_DIR" "$RES/runtime/audiveris"

# ---------------------------------------------------------------------------
# 3. Tesseract: copy the Homebrew binary plus eng/ita language data.
# ---------------------------------------------------------------------------
echo "[runtime] copying tesseract from Homebrew"
TESS_BIN="$(command -v tesseract || true)"
if [[ -z "$TESS_BIN" ]]; then
  echo "ERROR: tesseract is not installed. Run: brew install tesseract" >&2
  exit 1
fi
cp "$TESS_BIN" "$RES/tesseract/tesseract"
chmod +x "$RES/tesseract/tesseract"

mkdir -p "$RES/runtime/tessdata"
TESSDATA_SRC="$(dirname "$(readlink "$TESS_BIN" 2>/dev/null || echo "$TESS_BIN")")/../share/tessdata"
[[ -d "$TESSDATA_SRC" ]] || TESSDATA_SRC="$(brew --prefix tesseract 2>/dev/null)/share/tessdata"
for lang in eng ita; do
  if [[ -f "$TESSDATA_SRC/$lang.traineddata" ]]; then
    cp "$TESSDATA_SRC/$lang.traineddata" "$RES/runtime/tessdata/"
  else
    echo "WARN: $lang.traineddata not found under $TESSDATA_SRC" >&2
  fi
done

echo "[runtime] done. Layout:"
find "$RES" -maxdepth 3 -type d | sort

# ---------------------------------------------------------------------------
# Notes on shipping a Mac bundle:
# * Every embedded .dylib in runtime/audiveris and runtime/jre needs to be
#   codesigned individually before notarization. Use `codesign --deep` only
#   as a last resort — Apple's recent docs prefer per-file signing scripts.
# * The bundled JRE invalidates Hardened Runtime unless the entitlement
#   `com.apple.security.cs.allow-jit` is added; record it in
#   src-tauri/entitlements.plist before `tauri:build`.
