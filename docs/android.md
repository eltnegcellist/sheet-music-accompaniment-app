# Android build and self-hosted OMR

The Android edition reuses the existing React/Vite player but does **not**
bundle the Python/Audiveris sidecar. PDF recognition is performed by an OMR
server configured by the user inside the app.

## Architecture

1. Pick a PDF on Android.
2. The app uploads it to the configured `/analyze` endpoint.
3. The self-hosted backend runs Audiveris and returns MusicXML + measure layout.
4. Rendering, score following, tempo changes, looping and audio playback run on
   the Android device.

The server URL and optional API token are stored in Android WebView local
storage. They are never sent anywhere except the configured server.

## Start an OMR server

On a machine with Docker:

```bash
git clone https://github.com/eltnegcellist/sheet-music-accompaniment-app.git
cd sheet-music-accompaniment-app
API_TOKEN="$(openssl rand -hex 24)" docker compose up -d backend
```

Expose port 8000 only on a trusted LAN, or put the service behind HTTPS when
accessing it over the Internet. Set the same `API_TOKEN` in the Android app.

For a permanent deployment, put `API_TOKEN=...` in a local `.env` file.
Do not commit that file.

## Build the APK locally

Requirements:

- Node.js 20+
- JDK 17
- Android SDK 35
- Gradle 8.9 (or Android Studio with a compatible Gradle installation)

```bash
cd frontend
npm ci
npx vite build
cd ..
rm -rf android/app/src/main/assets/www
mkdir -p android/app/src/main/assets/www
cp -R frontend/dist/. android/app/src/main/assets/www/
gradle -p android assembleDebug
```

The APK is created under:

`android/app/build/outputs/apk/debug/app-debug.apk`

GitHub Actions also builds a debug APK artifact automatically.

## Notes

- The Android wrapper intentionally permits cleartext HTTP so a server on a
  private home LAN can be used. Prefer HTTPS for any Internet-facing server.
- The app uses a packaged, trusted WebView UI. It enables file-origin network
  access so that UI can call the server chosen by the user.
- macOS desktop packaging remains unchanged and continues to use its bundled
  local sidecar.
