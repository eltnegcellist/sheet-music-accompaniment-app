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

mkdir -p "$RES/runtime"
# Old layout (resources/tesseract/) is replaced by runtime/tesseract/
# below. Clean it so leftovers from a previous run do not bloat the
# bundle or leave stale dylibs that load at runtime.
rm -rf "$RES/tesseract"

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
    --add-modules java.base,java.desktop,java.logging,java.management,java.naming,java.prefs,java.scripting,java.security.jgss,java.sql,java.xml,jdk.crypto.ec,jdk.localedata,jdk.unsupported,jdk.zipfs \
    --include-locales=en,ja \
    --no-header-files \
    --no-man-pages \
    --strip-debug \
    --compress=zip-6 \
    --output "$RES/runtime/jre"

# macOS 26 (Tahoe) attaches com.apple.provenance to every file written
# by tar/jlink, and Tauri's build.rs walker hits EACCES when it stats
# symlinks under jre/legal/ (modules' LICENSE/ADDITIONAL_LICENSE_INFO/
# ASSEMBLY_EXCEPTION are relative symlinks into ../java.base/). Strip
# xattrs and move legal/ outside resources/ so Tauri's bundle.resources
# glob never visits it. `tauri build` callers can copy the staged
# legal-bundle/ directory back before notarization to satisfy
# Adoptium's redistribution terms.
xattr -rc "$RES/runtime" 2>/dev/null || true
LEGAL_STAGE="$ROOT/frontend/src-tauri/legal-bundle"
if [[ -d "$RES/runtime/jre/legal" ]]; then
  rm -rf "$LEGAL_STAGE"
  mv "$RES/runtime/jre/legal" "$LEGAL_STAGE"
fi

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
# 3. Tesseract: bundle the Homebrew binary together with libtesseract,
#    libleptonica and their transitive deps via bundle_macho_macos.sh,
#    so the produced .app does not depend on Homebrew at runtime.
#    Output layout: resources/runtime/tesseract/{bin/tesseract,lib/*}.
# ---------------------------------------------------------------------------
echo "[runtime] bundling tesseract from Homebrew"
TESS_BIN="$(command -v tesseract || true)"
if [[ -z "$TESS_BIN" ]]; then
  echo "ERROR: tesseract is not installed. Run: brew install tesseract" >&2
  exit 1
fi
rm -rf "$RES/runtime/tesseract"
"$ROOT/scripts/bundle_macho_macos.sh" "$RES/runtime/tesseract" "$TESS_BIN"
xattr -rc "$RES/runtime/tesseract" 2>/dev/null || true

mkdir -p "$RES/runtime/tessdata"
TESSDATA_SRC="$(brew --prefix tesseract 2>/dev/null)/share/tessdata"
for lang in eng ita; do
  if [[ -f "$TESSDATA_SRC/$lang.traineddata" ]]; then
    cp "$TESSDATA_SRC/$lang.traineddata" "$RES/runtime/tessdata/"
  else
    echo "WARN: $lang.traineddata not found under $TESSDATA_SRC" >&2
  fi
done

# ---------------------------------------------------------------------------
# 4. Poppler: bundle pdftoppm/pdfinfo/etc. plus their transitive Homebrew
#    dylib deps so pdf2image (used by tempo OCR + the splitter fallback)
#    works on machines without Homebrew. bundle_macho_macos.sh walks
#    otool -L recursively and rewrites install names to @loader_path.
# ---------------------------------------------------------------------------
echo "[runtime] bundling Poppler from Homebrew"
POPPLER_PREFIX="$(brew --prefix poppler 2>/dev/null || true)"
if [[ -z "$POPPLER_PREFIX" || ! -d "$POPPLER_PREFIX/bin" ]]; then
  echo "ERROR: poppler is not installed. Run: brew install poppler" >&2
  exit 1
fi
rm -rf "$RES/runtime/poppler"
"$ROOT/scripts/bundle_macho_macos.sh" "$RES/runtime/poppler" \
    "$POPPLER_PREFIX/bin/pdftoppm" \
    "$POPPLER_PREFIX/bin/pdfinfo" \
    "$POPPLER_PREFIX/bin/pdfseparate" \
    "$POPPLER_PREFIX/bin/pdfunite" \
    "$POPPLER_PREFIX/bin/pdftocairo"
xattr -rc "$RES/runtime/poppler" 2>/dev/null || true

echo "[runtime] done. Layout:"
find "$RES" -maxdepth 3 -type d | sort

# ---------------------------------------------------------------------------
# Notes on shipping a Mac bundle:
# * Every binary tree under runtime/ is fully self-contained:
#     - runtime/jre        : jlink-built, JVM-internal dylibs only
#     - runtime/audiveris  : loads the bundled JRE explicitly
#     - runtime/poppler    : relinked via bundle_macho_macos.sh
#     - runtime/tesseract  : relinked via bundle_macho_macos.sh
#   So the produced .app does not depend on Homebrew on the end
#   user's Mac.
# * The build is unsigned (野良 distribution); ad-hoc signing happens
#   in scripts/sign_adhoc_macos.sh after `tauri:build`. End users
#   bypass Gatekeeper manually — see docs/macos_unsigned_distribution.md.
