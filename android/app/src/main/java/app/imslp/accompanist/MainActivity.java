package app.imslp.accompanist;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.OpenableColumns;
import android.webkit.JavascriptInterface;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.widget.Toast;

import androidx.webkit.WebViewAssetLoader;
import androidx.webkit.WebViewClientCompat;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

public class MainActivity extends Activity {
    private static final int FILE_CHOOSER_REQUEST = 1001;
    private static final int SAVE_DOCUMENT_REQUEST = 1002;
    private static final String APP_ORIGIN = "https://appassets.androidplatform.net";

    private WebView webView;
    private WebViewAssetLoader assetLoader;
    private ValueCallback<Uri[]> fileChooserCallback;

    private Uri pendingIncomingUri;
    private String pendingIncomingName;
    private String pendingIncomingMime;
    private boolean pageReady = false;

    private String pendingSaveText;
    private String pendingSaveName;
    private String pendingSaveMime;

    @SuppressLint({"SetJavaScriptEnabled", "AddJavascriptInterface"})
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        parseIncomingIntent(getIntent());

        assetLoader = new WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", new WebViewAssetLoader.AssetsPathHandler(this))
            .addPathHandler("/incoming/", this::serveIncomingFile)
            .build();

        webView = new WebView(this);
        setContentView(webView);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setUserAgentString(
            settings.getUserAgentString() + " IMSLPAccompanistAndroid/0.2.0"
        );

        webView.addJavascriptInterface(new AndroidBridge(), "AndroidBridge");
        webView.setWebViewClient(new WebViewClientCompat() {
            @Override
            public WebResourceResponse shouldInterceptRequest(
                WebView view,
                WebResourceRequest request
            ) {
                return assetLoader.shouldInterceptRequest(request.getUrl());
            }

            @Override
            @SuppressWarnings("deprecation")
            public WebResourceResponse shouldInterceptRequest(WebView view, String url) {
                return assetLoader.shouldInterceptRequest(Uri.parse(url));
            }

            @Override
            public boolean shouldOverrideUrlLoading(
                WebView view,
                WebResourceRequest request
            ) {
                return handleTopLevelNavigation(request.getUrl());
            }

            @Override
            @SuppressWarnings("deprecation")
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return handleTopLevelNavigation(Uri.parse(url));
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                pageReady = true;
                dispatchPendingIncomingFile();
            }

            @Override
            public boolean onRenderProcessGone(
                WebView view,
                RenderProcessGoneDetail detail
            ) {
                pageReady = false;
                Toast.makeText(
                    MainActivity.this,
                    "表示エンジンを再起動します",
                    Toast.LENGTH_SHORT
                ).show();
                runOnUiThread(MainActivity.this::recreate);
                return true;
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(
                WebView view,
                ValueCallback<Uri[]> filePathCallback,
                FileChooserParams fileChooserParams
            ) {
                if (fileChooserCallback != null) {
                    fileChooserCallback.onReceiveValue(null);
                }
                fileChooserCallback = filePathCallback;

                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("*/*");
                intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
                intent.putExtra(
                    Intent.EXTRA_MIME_TYPES,
                    new String[] {
                        "application/pdf",
                        "application/xml",
                        "text/xml",
                        "application/vnd.recordare.musicxml+xml"
                    }
                );
                startActivityForResult(intent, FILE_CHOOSER_REQUEST);
                return true;
            }
        });

        if (savedInstanceState == null) {
            webView.loadUrl(APP_ORIGIN + "/assets/www/index.html");
        } else {
            webView.restoreState(savedInstanceState);
        }
    }

    private boolean handleTopLevelNavigation(Uri uri) {
        if (uri == null) return true;
        if ("appassets.androidplatform.net".equals(uri.getHost())) {
            return false;
        }
        String scheme = uri.getScheme();
        if ("http".equalsIgnoreCase(scheme) || "https".equalsIgnoreCase(scheme)) {
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, uri));
            } catch (Exception ignored) {
                Toast.makeText(this, "リンクを開けませんでした", Toast.LENGTH_SHORT).show();
            }
        }
        return true;
    }

    private WebResourceResponse serveIncomingFile(String path) {
        if (!"current".equals(path) || pendingIncomingUri == null) {
            return response(
                "text/plain",
                404,
                "Not Found",
                new ByteArrayInputStream("Not Found".getBytes(StandardCharsets.UTF_8))
            );
        }

        try {
            InputStream input = getContentResolver().openInputStream(pendingIncomingUri);
            if (input == null) {
                return response(
                    "text/plain",
                    404,
                    "Not Found",
                    new ByteArrayInputStream(new byte[0])
                );
            }
            return response(
                pendingIncomingMime != null ? pendingIncomingMime : "application/octet-stream",
                200,
                "OK",
                input
            );
        } catch (Exception error) {
            return response(
                "text/plain",
                500,
                "Read failed",
                new ByteArrayInputStream(
                    error.toString().getBytes(StandardCharsets.UTF_8)
                )
            );
        }
    }

    private WebResourceResponse response(
        String mime,
        int status,
        String reason,
        InputStream input
    ) {
        Map<String, String> headers = new HashMap<>();
        headers.put("Cache-Control", "no-store");
        headers.put("Access-Control-Allow-Origin", APP_ORIGIN);
        return new WebResourceResponse(
            mime,
            null,
            status,
            reason,
            headers,
            input
        );
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        parseIncomingIntent(intent);
        dispatchPendingIncomingFile();
    }

    private void parseIncomingIntent(Intent intent) {
        if (intent == null) return;

        Uri uri = null;
        if (Intent.ACTION_VIEW.equals(intent.getAction())) {
            uri = intent.getData();
        } else if (Intent.ACTION_SEND.equals(intent.getAction())) {
            if (Build.VERSION.SDK_INT >= 33) {
                uri = intent.getParcelableExtra(Intent.EXTRA_STREAM, Uri.class);
            } else {
                //noinspection deprecation
                uri = intent.getParcelableExtra(Intent.EXTRA_STREAM);
            }
        }

        if (uri == null) return;
        String name = resolveDisplayName(uri);
        String mime = intent.getType();
        if (mime == null) mime = getContentResolver().getType(uri);
        if (!isSupportedScore(name, mime)) return;

        pendingIncomingUri = uri;
        pendingIncomingName = name != null ? name : "score.pdf";
        pendingIncomingMime = mime != null ? mime : "application/octet-stream";

        int flags = intent.getFlags();
        if ((flags & Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION) != 0) {
            try {
                getContentResolver().takePersistableUriPermission(
                    uri,
                    flags & (Intent.FLAG_GRANT_READ_URI_PERMISSION
                        | Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
                );
            } catch (SecurityException ignored) {
                // Most ACTION_VIEW senders only grant temporary read access.
            }
        }
    }

    private boolean isSupportedScore(String name, String mime) {
        String n = name == null ? "" : name.toLowerCase(Locale.ROOT);
        String m = mime == null ? "" : mime.toLowerCase(Locale.ROOT);
        return n.endsWith(".pdf")
            || n.endsWith(".xml")
            || n.endsWith(".musicxml")
            || "application/pdf".equals(m)
            || "application/xml".equals(m)
            || "text/xml".equals(m)
            || "application/vnd.recordare.musicxml+xml".equals(m);
    }

    private String resolveDisplayName(Uri uri) {
        if ("content".equalsIgnoreCase(uri.getScheme())) {
            try (Cursor cursor = getContentResolver().query(
                uri,
                new String[] { OpenableColumns.DISPLAY_NAME },
                null,
                null,
                null
            )) {
                if (cursor != null && cursor.moveToFirst()) {
                    int index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                    if (index >= 0) return cursor.getString(index);
                }
            } catch (Exception ignored) {
                // Fall back to the last path segment.
            }
        }
        return uri.getLastPathSegment();
    }

    private void dispatchPendingIncomingFile() {
        if (!pageReady || webView == null || pendingIncomingUri == null) return;

        try {
            JSONObject payload = new JSONObject();
            payload.put(
                "url",
                APP_ORIGIN + "/incoming/current?t=" + System.currentTimeMillis()
            );
            payload.put("name", pendingIncomingName);
            payload.put("mime", pendingIncomingMime);
            String json = payload.toString();
            webView.evaluateJavascript(
                "window.__ANDROID_PENDING_FILE__=" + json + ";"
                    + "window.dispatchEvent(new CustomEvent('android-incoming-file',"
                    + "{detail:" + json + "}));",
                null
            );
        } catch (JSONException ignored) {
            // Strings sourced from Android's content resolver should always encode.
        }
    }

    private final class AndroidBridge {
        @JavascriptInterface
        public void setKeepScreenOn(boolean keep) {
            runOnUiThread(() -> {
                if (webView != null) webView.setKeepScreenOn(keep);
            });
        }

        @JavascriptInterface
        public void setAllowHttpOmr(boolean allow) {
            runOnUiThread(() -> {
                if (webView == null) return;
                webView.getSettings().setMixedContentMode(
                    allow
                        ? WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
                        : WebSettings.MIXED_CONTENT_NEVER_ALLOW
                );
            });
        }

        @JavascriptInterface
        public void saveTextFile(String fileName, String mimeType, String content) {
            runOnUiThread(() -> {
                pendingSaveName =
                    (fileName == null || fileName.isEmpty()) ? "score.musicxml" : fileName;
                pendingSaveMime =
                    (mimeType == null || mimeType.isEmpty())
                        ? "application/octet-stream"
                        : mimeType;
                pendingSaveText = content != null ? content : "";

                Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType(pendingSaveMime);
                intent.putExtra(Intent.EXTRA_TITLE, pendingSaveName);
                startActivityForResult(intent, SAVE_DOCUMENT_REQUEST);
            });
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == FILE_CHOOSER_REQUEST) {
            Uri[] results = null;
            if (resultCode == RESULT_OK && data != null) {
                if (data.getClipData() != null) {
                    int count = data.getClipData().getItemCount();
                    results = new Uri[count];
                    for (int i = 0; i < count; i++) {
                        results[i] = data.getClipData().getItemAt(i).getUri();
                    }
                } else if (data.getData() != null) {
                    results = new Uri[] { data.getData() };
                }
            }
            if (fileChooserCallback != null) {
                fileChooserCallback.onReceiveValue(results);
                fileChooserCallback = null;
            }
            return;
        }

        if (requestCode == SAVE_DOCUMENT_REQUEST) {
            if (resultCode == RESULT_OK && data != null && data.getData() != null) {
                try (OutputStream output =
                    getContentResolver().openOutputStream(data.getData())) {
                    if (output == null) throw new IllegalStateException("No output stream");
                    output.write(
                        (pendingSaveText != null ? pendingSaveText : "")
                            .getBytes(StandardCharsets.UTF_8)
                    );
                    Toast.makeText(this, "MusicXMLを保存しました", Toast.LENGTH_SHORT).show();
                } catch (Exception error) {
                    Toast.makeText(
                        this,
                        "MusicXMLの保存に失敗しました",
                        Toast.LENGTH_LONG
                    ).show();
                }
            }
            pendingSaveText = null;
            pendingSaveName = null;
            pendingSaveMime = null;
            return;
        }

        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        webView.saveState(outState);
        super.onSaveInstanceState(outState);
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.setKeepScreenOn(false);
            webView.removeJavascriptInterface("AndroidBridge");
            webView.destroy();
        }
        super.onDestroy();
    }
}
