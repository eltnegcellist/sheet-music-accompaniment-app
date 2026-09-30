#!/usr/bin/env bash
set -euo pipefail
mkdir -p smoke-results
OLD="$RUNNER_TEMP/baseline.apk"
CURRENT="$RUNNER_TEMP/current/IMSLP-Accompanist-Android-v0.2.4.apk"
TEST="android/app/build/outputs/apk/androidTest/release/app-release-androidTest.apk"
adb reverse tcp:18765 tcp:18765
python3 scripts/android_upgrade_mock_server.py > smoke-results/fixture-server.log 2>&1 &
MOCK_PID=$!
trap 'kill "$MOCK_PID" 2>/dev/null || true; adb logcat -d > smoke-results/logcat.txt' EXIT
for attempt in {1..30}; do
  if curl --fail --silent http://127.0.0.1:18765/health >/dev/null; then break; fi
  sleep 1
done
run_phase() {
  timeout 150 adb shell am instrument -w -e phase "$1" \
    app.imslp.accompanist.test/app.imslp.accompanist.UpgradeSmokeInstrumentation \
    | tee "smoke-results/$1.txt"
  grep -q 'INSTRUMENTATION_RESULT: smoke_result=passed' "smoke-results/$1.txt"
  adb pull "/sdcard/Android/data/app.imslp.accompanist/files/$1.png" "smoke-results/$1.png"
}
adb install "$OLD"
adb install "$TEST"
run_phase seed
adb shell dumpsys package app.imslp.accompanist > smoke-results/package-before.txt
adb install -r "$CURRENT"
adb shell dumpsys package app.imslp.accompanist > smoke-results/package-after.txt
run_phase verify
curl --fail --silent http://127.0.0.1:18765/test/state > smoke-results/fixture-state.json
# Separate fresh-install-state check, after the update/data-retention checks have passed.
adb shell pm clear app.imslp.accompanist
run_phase fresh
printf '%s\n' 'Signed v0.2.3 -> v0.2.4 update and WebView smoke checks passed.' >> "$GITHUB_STEP_SUMMARY"
