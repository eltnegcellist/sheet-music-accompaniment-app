# Android v0.2.5 — mobile-first self-hosted OMR

The Android edition is designed as a **free/open-source, phone-first client with user-owned
OMR infrastructure**. v0.2.1 replaces the desktop-oriented drag/drop and wide
transport controls with a dedicated touch UI.

The Android app contains the score viewer, playback engine, local cache and
server settings. PDF recognition itself is performed by the user's own
FastAPI server, which can run **Audiveris**, neural **homr**, or confidence-gated **Hybrid**.

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
4. includes both Audiveris and a Python 3.11 homr 0.7 CPU runtime,
5. prints the server URL and API token to enter in Android.

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
2. choose **Audiveris**, **homr (neural OMR)**, or **Hybrid**,
3. enter the server URL,
4. enter the API token,
5. tap **接続テスト / Test connection**,
6. tap **保存 / Save**.

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
Audiveris  OR  neural homr  OR  Hybrid
   ↓
MusicXML
   ↓
Android local cache
   ↓
viewer / accompaniment playback
```

### Neural OMR notes

homr 0.7 uses a learned segmentation + transformer OMR pipeline. The server
runs it in an isolated Python 3.11 environment via `uvx`, because homr 0.7
requires Python 3.11+ while the existing FastAPI/Audiveris container uses the
Ubuntu 22.04 system Python.

The neural model assets are pre-downloaded when the server Docker image is
built. The first recognition after server start can still take longer because
the ONNX sessions must warm up. homr currently does not provide
Audiveris-compatible PDF measure bounding boxes,
so **PDF measure highlighting is disabled for homr output**. Score-view
playback still works.

Audiveris remains the default. Hybrid runs both engines, retains healthy
Audiveris structure and fuses only safely matched pitches, or chooses homr when
Audiveris fails or rhythm is clearly better. It costs additional server time.
The app checks /capabilities before uploading a Hybrid PDF and separates cached
results by engine. Hybrid PDF highlighting depends on the chosen layout.

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

Use the existing fixed release keystore from the private backup. **Do not generate
a replacement key.** The four secrets have been restored from the original key.

Keep the original keystore and passwords backed up privately. Losing the
signing key means existing installations cannot be updated with a newly signed
APK.

After tests and signature verification, main builds publish a prerelease with
the matching source tag and checksum. Download from [GitHub Releases](https://github.com/eltnegcellist/sheet-music-accompaniment-app/releases).

Release files:

```text
IMSLP-Accompanist-Android-v0.2.5.apk
IMSLP-Accompanist-v0.2.5-SHA256SUMS.txt
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

## Cloud validation and remaining device checks

The backend-and-audio-verification workflow reuses checked-in outputs from
Saint-Saens clean #413948 p8 (run 36667381289). It executes the real authenticated
HTTP API, parameter loading, production Hybrid fusion and engine cache isolation;
only the recognition drivers are replayed. Expected fusion is 25 measures,
170 notes, 81.3%. No new OMR benchmark is executed.

Chromium exercises the built Android UI, renders declaration-free Hybrid
MusicXML, measures non-silent Salamander piano audio, and checks completion,
live tempo changes, loop playback and silence after Stop. Evidence includes
screenshots, JSON results and waveform measurements.

The previous signed v0.2.3-to-v0.2.4 emulator update passed in run 36682924672,
including retained settings and IndexedDB scores. Physical Galaxy S25 update,
speaker output, share/import, MusicXML export, screen-awake behaviour and
new recognition runtime still require device checks. Do not uninstall the
fixed-signed v0.2.3 app; install the newer fixed-signed APK over it.
