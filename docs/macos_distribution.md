# macOS Distribution Guide

End-to-end recipe for producing a notarized, stapled, distributable
`IMSLP Accompanist.dmg` from a checkout of this repo.

## Prerequisites

### 1. Apple Developer Program membership

Notarization requires a paid Apple Developer Program account ($99/yr).

1. Sign up at <https://developer.apple.com/programs/enroll/>.
2. Apple verifies the account (individual: a few hours; organization:
   1–7 days, requires D-U-N-S number).
3. Once active, you have a **Team ID** — a 10-character alphanumeric
   identifier visible at <https://developer.apple.com/account>.

### 2. Developer ID Application certificate

This is the certificate that signs the `.app` and DMG.

1. Open **Xcode** → **Settings** → **Accounts**, sign in with your
   Apple ID, select your team, click **Manage Certificates...**, and
   create a **Developer ID Application** certificate. Xcode handles
   the CSR + private key generation automatically.
2. Verify the cert is in the login keychain:
   ```sh
   security find-identity -v -p codesigning
   ```
   Look for `Developer ID Application: <Your Name> (<TEAMID>)`. Copy
   the full string — that is your `SIGN_IDENTITY`.

If the certificate exists in your developer account but not on this
machine, export it from the original machine as a `.p12` and import
it in Keychain Access.

### 3. notarytool credentials

`notarytool` authenticates with an app-specific password stored as a
keychain profile.

1. Generate an app-specific password at <https://appleid.apple.com>
   → Sign-In and Security → App-Specific Passwords.
2. Store it as a keychain profile (one-time setup):
   ```sh
   xcrun notarytool store-credentials "imslp-accompanist" \
       --apple-id  "your-apple-id@example.com" \
       --team-id   "ABCDE12345" \
       --password  "abcd-efgh-ijkl-mnop"
   ```
   The profile name (`imslp-accompanist` here) is what you pass as
   `NOTARY_PROFILE` to the signing script.

### 4. Build prerequisites

```sh
brew install tesseract poppler gradle git
```

Plus the standard toolchain: Xcode Command Line Tools, Rust, Node 18+,
Python 3.11+ (for the sidecar build).

## Build pipeline

```sh
# 0. Stage the bundled runtime tree (JRE, Audiveris, Tesseract, Poppler).
#    Run once, or whenever Audiveris/JRE/Poppler versions change.
scripts/fetch_runtime_macos.sh

# 1. Build the PyInstaller sidecar (--onefile mode for production).
scripts/build_sidecar.sh --onefile

# 2. Build the .app via Tauri. We deliberately set
#    bundle.targets = ["app"] in tauri.conf.json — Tauri 1.x's
#    DMG bundler is unreliable on macOS Tahoe, so we drive DMG
#    creation ourselves in step 5.
npm run tauri:build --prefix frontend

# 3. Restore the Adoptium legal/ tree into the .app.
#    fetch_runtime_macos.sh stages it outside resources/ to keep
#    Tauri's resource walker out of provenance-tagged symlinks.
scripts/post_bundle_macos.sh

# 4. Sign every nested Mach-O, sign the .app, notarize, staple.
export SIGN_IDENTITY="Developer ID Application: Your Name (ABCDE12345)"
export NOTARY_PROFILE="imslp-accompanist"
scripts/sign_and_notarize_macos.sh

# 5. Wrap the signed/stapled .app into a DMG; sign + notarize the DMG.
scripts/build_dmg_macos.sh

# Output: dist/IMSLP-Accompanist-<version>.dmg
```

## Verifying a release

```sh
# Confirm the .app passes Gatekeeper.
spctl --assess --type execute --verbose=4 \
    "frontend/src-tauri/target/release/bundle/macos/IMSLP Accompanist.app"
# Expected: "accepted source=Notarized Developer ID"

# Confirm the DMG is stapled.
xcrun stapler validate dist/IMSLP-Accompanist-*.dmg
# Expected: "The validate action worked!"

# Smoke-test on a clean Mac (or one that has never opened this app):
#   1. Download the DMG, double-click, drag to /Applications.
#   2. Launch from /Applications. Gatekeeper should NOT prompt — if
#      it does, notarization or stapling did not complete.
```

## Troubleshooting

### `notarytool submit` fails with "The signature ... does not include
a secure timestamp"

The `--timestamp` flag is missing somewhere. `sign_and_notarize_macos.sh`
includes it on every codesign call; if you sign manually, always pass
`--timestamp`.

### `notarytool log <uuid>` reports specific binaries as unsigned

Apple has tightened the rules — every Mach-O inside the bundle must
carry the Hardened Runtime flag and the same Developer ID. Re-run
`sign_and_notarize_macos.sh`; it walks the tree leaf-up so nothing
is missed.

If a *newly added* binary trips this, check:
- It actually got copied into `.app/Contents/Resources/...` (i.e.
  `tauri.conf.json`'s `bundle.resources` glob covers it).
- It is identifiable as Mach-O by `file(1)` — the script's filter
  is `file ... | grep -qE 'Mach-O|dynamically linked'`.

### `xcrun stapler staple` fails with "could not find the staple"

The notarization log is not yet visible to the stapler. Wait 30s and
retry. If it persistently fails, check `xcrun notarytool log <uuid>`
for the actual rejection reason — sometimes notarization "succeeds"
but the ticket is delayed; sometimes it actually failed and the
script's exit-on-failure didn't catch a transient response.

### App crashes on launch with "killed: 9" right after Gatekeeper accepts

Hardened Runtime is rejecting something at runtime. Check
`Console.app` for `amfid` denial messages. Usually one of:
- Missing `com.apple.security.cs.allow-jit` (JVM)
- Missing `com.apple.security.cs.disable-library-validation`
  (loading dylibs not signed by us)
- A nested binary lost its signature (re-run signing)

The current `entitlements.plist` covers all three for this app.

## Tesseract follow-up

`runtime/poppler/` is fully self-contained (relinked via
`scripts/bundle_macho_macos.sh`). `resources/tesseract/tesseract`
is **not** — it still resolves `libtesseract.X.dylib` and
`libleptonica.X.dylib` from Homebrew at runtime, which means
the produced .app only works on Macs that have Poppler... wait,
sorry, that have **Tesseract** installed via Homebrew.

For a real distribution, run tesseract through `bundle_macho_macos.sh`
the same way Poppler is, and update `main.rs`'s `TESSERACT_CMD` path
accordingly. This is the largest remaining task before the DMG is
truly portable; tracked separately.
