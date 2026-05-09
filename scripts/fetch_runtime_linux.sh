#!/usr/bin/env bash
# Assemble the bundled runtime tree the Tauri sidecar expects, for
# Linux x86_64 only. macOS/Windows variants need their own scripts
# because Audiveris doesn't ship a cross-platform tarball — see the
# notes at the end of this file.
#
# Output layout (matches frontend/src-tauri/src/main.rs env wiring):
#
#   frontend/src-tauri/resources/
#     runtime/
#       jre/                     <- Eclipse Temurin 25 JRE (jlink-trimmed)
#       audiveris/               <- Audiveris install tree (bin/ + lib/)
#       tessdata/                <- Tesseract language packs (eng.traineddata, ita.traineddata)
#     tesseract/
#       tesseract                <- Tesseract binary (system copy)
#
# Usage:
#     scripts/fetch_runtime_linux.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RES="$ROOT/frontend/src-tauri/resources"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$RES/runtime" "$RES/tesseract"

# Audiveris 5.10.2's build.gradle requires Java 25, so the bundled runtime
# must be at least JDK 25 GA. We fetch the JDK (not the JRE) artifact so
# jlink + jmods are available for trimming.
JRE_FEATURE="${JRE_FEATURE:-25}"
JRE_URL="https://api.adoptium.net/v3/binary/latest/${JRE_FEATURE}/ga/linux/x64/jdk/hotspot/normal/eclipse"
AUDIVERIS_VERSION="5.10.2"
AUDIVERIS_DEB_URL="https://github.com/Audiveris/audiveris/releases/download/${AUDIVERIS_VERSION}/Audiveris-${AUDIVERIS_VERSION}.deb"

# ---------------------------------------------------------------------------
# 1. Trimmed JRE via jlink. Pulls the full JDK once, runs jlink, keeps only
#    the resulting custom runtime; saves ~150MB vs shipping the whole JRE.
# ---------------------------------------------------------------------------
echo "[runtime] fetching latest Temurin JDK $JRE_FEATURE GA"
curl -fsSL "$JRE_URL" -o "$WORK/jdk.tgz"
mkdir -p "$WORK/jdk"
tar -xzf "$WORK/jdk.tgz" -C "$WORK/jdk" --strip-components=1
if [[ ! -x "$WORK/jdk/bin/jlink" ]]; then
  echo "ERROR: jlink not found in extracted JDK at $WORK/jdk" >&2
  exit 1
fi

echo "[runtime] running jlink to produce a minimal runtime"
rm -rf "$RES/runtime/jre"
"$WORK/jdk/bin/jlink" \
    --module-path "$WORK/jdk/jmods" \
    --add-modules java.base,java.desktop,java.logging,java.management,java.naming,java.prefs,java.scripting,java.security.jgss,java.sql,java.xml,jdk.crypto.ec,jdk.localedata,jdk.unsupported,jdk.zipfs \
    --include-locales=en,ja \
    --no-header-files \
    --no-man-pages \
    --strip-debug \
    --compress=zip-6 \
    --output "$RES/runtime/jre"

# ---------------------------------------------------------------------------
# 2. Audiveris — extract the .deb without installing it system-wide so we
#    can ship just the relevant files.
# ---------------------------------------------------------------------------
echo "[runtime] fetching Audiveris $AUDIVERIS_VERSION"
curl -fsSL "$AUDIVERIS_DEB_URL" -o "$WORK/audiveris.deb"
mkdir -p "$WORK/audiveris-extracted"
( cd "$WORK/audiveris-extracted" && ar x "$WORK/audiveris.deb" data.tar.xz && tar -xJf data.tar.xz )

# The .deb lays files out under /opt/audiveris (or /opt/Audiveris depending
# on version). Copy whichever exists.
rm -rf "$RES/runtime/audiveris"
mkdir -p "$RES/runtime/audiveris"
for src in "$WORK/audiveris-extracted/opt/audiveris" "$WORK/audiveris-extracted/opt/Audiveris"; do
  if [[ -d "$src" ]]; then
    cp -r "$src/." "$RES/runtime/audiveris/"
    break
  fi
done

if [[ ! -x "$RES/runtime/audiveris/bin/Audiveris" ]]; then
  echo "ERROR: Audiveris launcher not found after extraction." >&2
  ls "$WORK/audiveris-extracted/opt" >&2 || true
  exit 1
fi

# ---------------------------------------------------------------------------
# 3. Tesseract: the system package is the simplest source on Linux.
#    Copy the binary and the language data the OCR module loads.
# ---------------------------------------------------------------------------
echo "[runtime] copying tesseract from the system"
TESS_BIN="$(command -v tesseract || true)"
if [[ -z "$TESS_BIN" ]]; then
  echo "ERROR: tesseract is not installed. Run: sudo apt-get install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-ita" >&2
  exit 1
fi
cp "$TESS_BIN" "$RES/tesseract/tesseract"
chmod +x "$RES/tesseract/tesseract"

mkdir -p "$RES/runtime/tessdata"
TESSDATA_SRC="$(dirname "$(readlink -f "$TESS_BIN")")/../share/tessdata"
if [[ ! -d "$TESSDATA_SRC" ]]; then
  TESSDATA_SRC="/usr/share/tesseract-ocr/4.00/tessdata"
fi
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
# macOS / Windows notes
# ---------------------------------------------------------------------------
# * JRE: swap JRE_URL for the matching mac/win archive from Temurin.
# * Audiveris: there is no precompiled mac/win tarball on GitHub.
#   Build from source via `./gradlew installDist` against the upstream
#   repo, then copy build/install/Audiveris into resources/runtime/audiveris/.
# * Tesseract: bundle a static build (e.g. UB Mannheim build on Windows,
#   Homebrew tesseract on mac) and its tessdata directory.
