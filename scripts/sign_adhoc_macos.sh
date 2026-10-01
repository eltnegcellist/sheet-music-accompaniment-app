#!/usr/bin/env bash
# Sign each nested Mach-O, then seal and verify the application bundle.
# Ad-hoc signing does not provide Apple notarization.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_PATH_DEFAULT="$ROOT/frontend/src-tauri/target/release/bundle/macos/IMSLP Accompanist.app"
APP="${APP_PATH:-$APP_PATH_DEFAULT}"
[[ -d "$APP" ]] || { echo "App bundle missing: $APP" >&2; exit 1; }
python3 - "$APP" <<'PY'
from pathlib import Path
import subprocess
import sys

app = Path(sys.argv[1])
magics = {
    b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
    b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca",
}
signed = 0
for path in sorted((app / "Contents").rglob("*")):
    if not path.is_file() or path.is_symlink():
        continue
    if not (path.name.endswith((".dylib", ".so")) or path.stat().st_mode & 0o111):
        continue
    with path.open("rb") as file:
        magic = file.read(4)
    if magic not in magics:
        continue
    print("[adhoc] " + str(path.relative_to(app)), flush=True)
    subprocess.run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(path)], check=True)
    signed += 1
print(f"[adhoc] signed {signed} nested Mach-O files", flush=True)
subprocess.run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(app)], check=True)
subprocess.run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)], check=True)
PY
