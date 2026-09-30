package app.imslp.accompanist;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.graphics.Bitmap;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.WebView;
import org.json.JSONObject;
import org.json.JSONTokener;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** Runs against the actual signed release APK, including the old installed version. */
public class UpgradeSmokeInstrumentation extends Instrumentation {
    private Bundle args;
    private Activity activity;
    private WebView web;

    @Override public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        args = arguments;
        start();
    }

    @Override public void onStart() {
        Bundle result = new Bundle();
        String phase = args.getString("phase", "");
        try {
            PackageInfo info = getTargetContext().getPackageManager()
                .getPackageInfo("app.imslp.accompanist", 0);
            String expected = phase.equals("seed") ? "0.2.3" : "0.2.4";
            int code = phase.equals("seed") ? 5 : 6;
            if (!expected.equals(info.versionName) || info.getLongVersionCode() != code) {
                throw new AssertionError("Unexpected installed package version");
            }
            Intent intent = new Intent();
            intent.setClassName("app.imslp.accompanist", "app.imslp.accompanist.MainActivity");
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            activity = startActivitySync(intent);
            runOnMainSync(() -> web = findWebView(activity.findViewById(android.R.id.content)));
            if (web == null) throw new AssertionError("Release WebView missing");
            long deadline = SystemClock.elapsedRealtime() + 90000;
            while (!Boolean.TRUE.equals(eval("!!document.querySelector('.app--android')"))) {
                if (SystemClock.elapsedRealtime() > deadline) throw new AssertionError("UI did not load");
                SystemClock.sleep(200);
            }
            try (InputStream input = getContext().getAssets().open("upgrade-smoke.js")) {
                String script = new String(input.readAllBytes(), StandardCharsets.UTF_8);
                eval("window.__UPGRADE_PHASE__=" + JSONObject.quote(phase) + ";" + script);
            }
            deadline = SystemClock.elapsedRealtime() + 90000;
            while (true) {
                Object value = eval("JSON.stringify(window.__UPGRADE_RESULT__ || null)");
                if (value instanceof String && !value.equals("null")) {
                    JSONObject state = new JSONObject((String) value);
                    if (state.has("error")) throw new AssertionError(state.getString("error"));
                    if (state.optBoolean("passed")) {
                        result.putString("checks", state.getJSONArray("checks").toString());
                        break;
                    }
                }
                if (SystemClock.elapsedRealtime() > deadline) throw new AssertionError("Smoke phase timed out");
                SystemClock.sleep(200);
            }
            File dir = getTargetContext().getExternalFilesDir(null);
            Bitmap shot = getUiAutomation().takeScreenshot();
            if (dir != null && shot != null) {
                try (FileOutputStream out = new FileOutputStream(new File(dir, phase + ".png"))) {
                    shot.compress(Bitmap.CompressFormat.PNG, 100, out);
                }
                shot.recycle();
            }
            result.putString("smoke_result", "passed");
            result.putString("phase", phase);
            finish(Activity.RESULT_OK, result);
        } catch (Throwable failure) {
            result.putString("smoke_result", "failed");
            result.putString("phase", phase);
            result.putString("error", failure.toString());
            finish(Activity.RESULT_CANCELED, result);
        }
    }

    private WebView findWebView(View view) {
        if (view instanceof WebView) return (WebView) view;
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int i = 0; i < group.getChildCount(); i++) {
                WebView found = findWebView(group.getChildAt(i));
                if (found != null) return found;
            }
        }
        return null;
    }

    private Object eval(String script) throws Exception {
        CountDownLatch done = new CountDownLatch(1);
        AtomicReference<String> raw = new AtomicReference<>();
        runOnMainSync(() -> web.evaluateJavascript(script, value -> {
            raw.set(value);
            done.countDown();
        }));
        if (!done.await(20, TimeUnit.SECONDS)) throw new AssertionError("JS callback timed out");
        return new JSONTokener(raw.get()).nextValue();
    }
}
