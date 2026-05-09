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

is_external() {
  case "$1" in
    /opt/homebrew/*) return 0;;
    /usr/local/*)    return 0;;
    *) return 1;;
  esac
}

# Print every LC_RPATH path embedded in $1 (one per line).
get_rpaths() {
  otool -l "$1" \
    | awk '/cmd LC_RPATH/{flag=1; next} flag && /^[[:space:]]*path /{print $2; flag=0}'
}

# Resolve an @rpath/<suffix> dependency against $1's LC_RPATH list.
# Prints the absolute on-disk path of the first match, or returns 1.
resolve_rpath_dep() {
  local binary="$1"
  local dep="$2"
  local suffix="${dep#@rpath/}"
  local rp candidate
  while IFS= read -r rp; do
    [[ -z "$rp" ]] && continue
    case "$rp" in
      @loader_path*)     rp="$(cd "$(dirname "$binary")" && pwd)/${rp#@loader_path/}";;
      @executable_path*) rp="$(cd "$(dirname "$binary")" && pwd)/${rp#@executable_path/}";;
    esac
    candidate="$rp/$suffix"
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done < <(get_rpaths "$binary")
  return 1
}

# Copy an external dylib into DEST_LIB and recurse into it. Idempotent
# via dest-file existence check (bash 3.2 compatible).
absorb_lib() {
  local src="$1"
  local base="$2"
  local dest="$DEST_LIB/$base"
  if [[ ! -f "$dest" ]]; then
    cp "$src" "$dest"
    chmod +w "$dest"
    install_name_tool -id "$base" "$dest"
    walk "$dest" "@loader_path"
  fi
}

# Walk a Mach-O file's dylib deps recursively. $2 is the install-name
# prefix to write into $1's load commands ("@loader_path/../lib" for
# binaries, "@loader_path" for sibling dylibs). Handles both absolute
# Homebrew/local-prefix references and @rpath/ references resolved
# through the binary's LC_RPATH list.
walk() {
  local target="$1"
  local prefix="$2"
  local dep base resolved
  while IFS= read -r dep; do
    [[ -z "$dep" ]] && continue
    case "$dep" in
      @rpath/*)
        if resolved="$(resolve_rpath_dep "$target" "$dep")"; then
          is_external "$resolved" || continue
          base="$(basename "$resolved")"
          absorb_lib "$resolved" "$base"
          install_name_tool -change "$dep" "$prefix/$base" "$target"
        fi
        ;;
      /*)
        is_external "$dep" || continue
        base="$(basename "$dep")"
        absorb_lib "$dep" "$base"
        install_name_tool -change "$dep" "$prefix/$base" "$target"
        ;;
    esac
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

bins_count="$(find "$DEST_BIN" -type f | wc -l | tr -d ' ')"
libs_count="$(find "$DEST_LIB" -type f | wc -l | tr -d ' ')"
echo "[bundle] $DEST: $bins_count bins, $libs_count libs"
