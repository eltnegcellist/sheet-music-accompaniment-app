# Android v0.2.2 — mobile-first self-hosted OMR

The Android edition is designed as a **free/open-source, phone-first client with user-owned
OMR infrastructure**. v0.2.1 replaces the desktop-oriented drag/drop and wide
transport controls with a dedicated touch UI.

The Android app contains the score viewer, playback engine, local cache and
server settings. PDF recognition itself is performed by the user's own
Audiveris/FastAPI server.

## Mobile-first UI

- Home screen uses a large **Choose score PDF** button instead of drag-and-drop.
- Recent scores are large tap targets with always-visible delete controls.
- Loaded scores use a compact Android app bar and a PDF/Score segmented switch.
- Playback uses a thumb-reachable bottom bar with a large Play/Stop button.
- Tempo, volume, range, loop, metronome, count-in and solo settings live in an expandable bottom sheet.
- The initial Android score zoom is tuned for phone-width display.

## What works on Android

- Pick a PDF from Android's document picker.
- Open/share a PDF directly into **IMSLP Accompanist** from another app.
- Upload the PDF to a user-configured OMR server.
- Receive MusicXML + measure layout and follow the source PDF during playback.
- Tempo, accompaniment volume, play range, loop, count-in and metronome.
- Solo-part playback when a solo part is detected.
- Save the generated MusicXML with Android's system file picker.
- Keep the screen awake while playback is active.
- Store the analyzed PDF + analysis result on the Android device.
- Re-open previously analyzed scores without contacting the OMR server.

The OMR server is only required when analyzing or re-analyzing a score.

## 1. Start your own OMR server

The easiest supported setup is Docker on a PC, NAS or VM.

```bash
git clone https://github.com/eltnegcellist/sheet-music-accompaniment-app.git
cd sheet-music-accompaniment-app
sh scripts/setup_omr_server.sh
```

The script:

1. generates a random API token,
2. stores it in the ignored `.omr-server.env` file,
3. builds and starts the production OMR container,
4. prints the server URL and API token to enter in Android.

The production compose file is `docker-compose.server.yml`. It uses persistent
volumes for the OMR result cache and Audiveris state and restarts automatically.

### Home LAN

If the phone and server are on the same Wi-Fi/LAN, enter the printed address,
for example:

```text
Server URL: http://192.168.1.20:8000
API token:  <generated token>
```

Android permits cleartext HTTP specifically so private-LAN servers work without
requiring local TLS certificates.

Do **not** expose that plain-HTTP port directly to the Internet.

### Internet-facing server

Put the OMR service behind HTTPS (Caddy, nginx, Cloud Run, a reverse proxy, etc.)
and use the HTTPS URL in the app. Keep `API_TOKEN` enabled.

The API token is sent only to the server URL configured by the user.

## 2. Configure the Android app

On first launch:

1. tap **OMR** in the top bar,
2. enter the server URL,
3. enter the API token,
4. tap **接続テスト / Test connection**,
5. tap **保存 / Save**.

If Android receives a PDF through **Open with** before a server is configured,
the app keeps that file pending, opens server setup and starts analysis after
the settings are saved.

## 3. Analyze and play

Choose a PDF from the app or use **Open with IMSLP Accompanist** from a file
manager/browser.

The first analysis follows this path:

```text
Android PDF
   ↓
user-owned FastAPI server
   ↓
Audiveris OMR
   ↓
MusicXML + measure layout
   ↓
Android local cache
   ↓
viewer / accompaniment playback
```

After analysis, the PDF and parsed response are stored in Android WebView
IndexedDB. The **Recently opened** list on Android is therefore device-local,
not the server's cache.

Deleting an Android recent item deletes only the local copy. The server may
still have its own OMR cache.

## Android security model

The packaged UI is served through AndroidX `WebViewAssetLoader` at
`https://appassets.androidplatform.net`.

The Android build explicitly disables:

- `file://` access,
- file-to-file URL access,
- universal access from `file://` URLs.

External top-level links are opened in the system browser instead of being
navigated inside the app WebView.

The native JavaScript bridge exposes only two app-owned operations:

- save generated MusicXML with Android's document picker,
- keep the screen awake while playback is running.

## Build a debug APK

Requirements:

- Node.js 20+
- JDK 17
- Android SDK 35
- Gradle 8.9

```bash
cd frontend
npm ci
npm test
npx vite build
cd ..

rm -rf android/app/src/main/assets/www
mkdir -p android/app/src/main/assets/www
cp -R frontend/dist/. android/app/src/main/assets/www/

gradle -p android assembleDebug
```

Output:

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

GitHub Actions runs the same build and publishes
`IMSLP-Accompanist-Android-debug` as an artifact.

## Signed GitHub releases

Do not use a newly generated debug key for every public build: Android treats
APKs signed by different keys as different update chains.

The repository includes `.github/workflows/android-release.yml`, which builds
a release APK with one stable signing key and can attach it to a tagged GitHub
Release.

Configure these repository secrets once:

- `ANDROID_KEYSTORE_BASE64`
- `ANDROID_KEYSTORE_PASSWORD`
- `ANDROID_KEY_ALIAS`
- `ANDROID_KEY_PASSWORD`

Example one-time keystore creation:

```bash
keytool -genkeypair \
  -keystore imslp-accompanist-release.jks \
  -alias imslp-accompanist \
  -keyalg RSA -keysize 4096 -validity 10000
```

Encode the keystore for the GitHub secret:

```bash
base64 < imslp-accompanist-release.jks | tr -d '\n'
```

Keep the original keystore and passwords backed up privately. Losing the
signing key means existing installations cannot be updated with a newly signed
APK.

After the secrets are configured, pushing a tag such as `v0.2.0` builds,
verifies and attaches:

```text
IMSLP-Accompanist-Android-v0.2.0.apk
```

## Desktop compatibility

The macOS desktop edition is unchanged:

- it still launches the bundled Python/Audiveris sidecar,
- it still prefers `window.__BACKEND_URL__`,
- Android-only server settings and IndexedDB score cache are not shown or used
  on the desktop app.


## Stable Android update signature

Starting with **v0.2.2**, installable Android releases use one fixed signing
certificate. This is what allows Android to install a newer APK as an update
instead of requiring uninstall/reinstall.

Pinned signing certificate SHA-256:

```text
AF:B1:4F:54:F7:34:FA:B5:64:A9:3F:35:49:E3:E7:33:F1:FC:97:F3:FE:83:AE:1C:84:3A:F4:7C:41:B2:5B:E3
```

The public certificate is committed at:

`android/signing/imslp-accompanist-release-cert.pem`

The private keystore is **never committed**. GitHub Actions receives it only
through repository secrets and verifies all three of the following before an
APK is published:

1. the committed public certificate fingerprint,
2. the private keystore certificate fingerprint,
3. the certificate fingerprint embedded in the finished APK.

All three must match the pinned fingerprint above.

### One-time migration from v0.2.1 debug APK

The previously distributed v0.2.1 debug APK was signed by an ephemeral GitHub
runner debug key. That private key no longer exists, so Android cannot accept
v0.2.2 fixed-signing APK as an in-place update over v0.2.1.

Therefore **one final uninstall/reinstall is required when moving from v0.2.1
to v0.2.2**. After v0.2.2 is installed, later fixed-signed builds can be
installed normally as updates as long as `versionCode` increases.

Do not distribute APKs from the ordinary `android-ci` debug artifact as user
updates. Those artifacts are test builds only. Use the
`android-stable-release` workflow artifact or tagged GitHub Release.
