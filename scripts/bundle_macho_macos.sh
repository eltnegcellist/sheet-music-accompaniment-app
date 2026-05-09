#!/usr/bin/env bash
# Self-contained macOS Mach-O bundler.
#
# Copies one or more Mach-O binaries plus their Homebrew/local-prefix
# dylib dependencies into <dest>/{bin,lib} and rewrites their install
# names so the resulting tree is independent of Homebrew on the end
# user's machine.
#
# Usage:
#     bundle_macho_macos.sh <dest_root> <binary_path>...
#
# Layout produced:
#     <dest_root>/bin/<binary_name>          (copied + relinked)
#     <dest_root>/lib/lib<...>.dylib         (transitive deps)
#
# Install-name rules:
#     - In bin/<...>:        external deps -> @loader_path/../lib/<base>
#     - In lib/<...>.dylib:  external deps -> @loader_path/<base>
#     - Each dylib's LC_ID_DYLIB rewritten to its bare basename
#
# Each modified Mach-O is ad-hoc resigned after install_name_tool
# mutation; macOS Sonoma+ rejects the modified header otherwise.
#
# "External" here means anything under /opt/homebrew/ or /usr/local/.
# /usr/lib/ and /System/Library/ deps live in dyld shared cache and
# are intentionally skipped.

set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <dest_root> <binary_path>..." >&2
  exit 1
fi

DEST="$1"
shift

DEST_BIN="$DEST/bin"
DEST_LIB="$DEST/lib"
mkdir -p "$DEST_BIN" "$DEST_LIB"

declare -A copied_libs=()

is_external() {
  case "$1" in
    /opt/homebrew/*) return 0;;
    /usr/local/*)    return 0;;
    *) return 1;;
  esac
}

# Walk a Mach-O file's dylib deps recursively. $2 is the install-name
# prefix to write into $1's load commands ("@loader_path/../lib" for
# binaries, "@loader_path" for sibling dylibs).
walk() {
  local target="$1"
  local prefix="$2"
  local dep base dest
  while IFS= read -r dep; do
    [[ -z "$dep" ]] && continue
    is_external "$dep" || continue
    base="$(basename "$dep")"
    dest="$DEST_LIB/$base"
    if [[ -z "${copied_libs[$base]:-}" ]]; then
      cp "$dep" "$dest"        # cp follows symlinks; we get the real file
      chmod +w "$dest"
      copied_libs["$base"]=1
      install_name_tool -id "$base" "$dest"
      walk "$dest" "@loader_path"
    fi
    install_name_tool -change "$dep" "$prefix/$base" "$target"
  done < <(otool -L "$target" | tail -n +2 | awk '{print $1}')
}

for bin_path in "$@"; do
  if [[ ! -x "$bin_path" ]]; then
    echo "ERROR: $bin_path not found or not executable." >&2
    exit 1
  fi
  base="$(basename "$bin_path")"
  dest="$DEST_BIN/$base"
  cp "$bin_path" "$dest"
  chmod +w "$dest"
  walk "$dest" "@loader_path/../lib"
done

# install_name_tool invalidates the existing codesignature. Ad-hoc
# resign so dyld will load the modified Mach-O on Sonoma+.
while IFS= read -r -d '' f; do
  codesign --force --sign - --timestamp=none "$f" 2>/dev/null || true
done < <(find "$DEST" -type f \( -perm -u=x -o -name "*.dylib" \) -print0)

echo "[bundle] $DEST: $(ls "$DEST_BIN" | wc -l | tr -d ' ') bins, ${#copied_libs[@]} libs"
