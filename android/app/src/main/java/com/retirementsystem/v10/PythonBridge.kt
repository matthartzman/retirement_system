package com.retirementsystem.v10

import android.content.ContentValues
import android.content.Context
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.util.Base64
import android.util.Log
import android.webkit.JavascriptInterface
import android.webkit.WebView
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import org.json.JSONObject
import java.io.File
import java.util.concurrent.Executors

private const val TAG = "PythonBridge"

/**
 * The Kotlin half of the third transport described in
 * documentation/ANDROID_MOBILE_ENHANCEMENT_PLAN.md: same route registry the
 * desktop js_api and server mode use, reached through Chaquopy instead of
 * PyWebView or a real HTTP socket.
 *
 * `request()` is deliberately void, not a return-value method: WebView's
 * `addJavascriptInterface` methods run synchronously from JS's point of view
 * (the calling JS thread blocks until the method returns), which would freeze
 * the UI for the duration of a workbook build. Work is dispatched onto
 * [executor] instead, and the result is delivered back to JS via
 * `evaluateJavascript` once it's ready — see frontend/js/android_bridge.js's
 * matching pending-request table.
 */
class PythonBridge(private val context: Context, private val webView: WebView) {

    private val executor = Executors.newSingleThreadExecutor()
    private val androidApiModule: PyObject = Python.getInstance().getModule("android_api")

    init {
        androidApiModule.callAttr("configure", context.filesDir.absolutePath)
        seedFirstRunIfNeeded()
    }

    /**
     * Materializes blank input/ CSVs on first launch by calling the same
     * POST /api/plan-data/blank route the in-app "Start New Plan" button
     * uses — reusing that existing, tested logic instead of bundling and
     * maintaining a second copy of the blank-template format here.
     */
    private fun seedFirstRunIfNeeded() {
        val marker = File(context.filesDir, "local_state/.android_first_run_complete")
        if (marker.exists()) return
        executor.execute {
            try {
                val result = callApi("POST", "/api/plan-data/blank", null, null)
                if (JSONObject(result).optBoolean("success", false)) {
                    marker.parentFile?.mkdirs()
                    marker.writeText("seeded")
                } else {
                    Log.w(TAG, "First-run seeding did not report success: $result")
                }
            } catch (e: Exception) {
                Log.e(TAG, "First-run seeding failed", e)
            }
        }
    }

    private fun callApi(method: String, url: String, bodyJsonText: String?, bodyText: String?): String {
        return androidApiModule.callAttr("get_api")
            .callAttr("request_json", method, url, bodyJsonText, bodyText)
            .toString()
    }

    /** Called from JS: window.AndroidBridge.request(method, url, bodyJsonText, bodyText, requestId). */
    @JavascriptInterface
    fun request(method: String, url: String, bodyJsonText: String?, bodyText: String?, requestId: String) {
        executor.execute {
            val resultJson = try {
                callApi(method, url, bodyJsonText, bodyText)
            } catch (e: Exception) {
                Log.e(TAG, "request($method $url) failed", e)
                JSONObject().put("success", false).put("error", e.message ?: e.toString()).toString()
            }
            deliver(requestId, resultJson)
        }
    }

    /**
     * Called from JS with a base64 `_binary` payload (workbook/PDF/.rpx
     * exports) to persist into the public Downloads collection — Android
     * WebView does not reliably surface `blob:` URL downloads the way a
     * desktop browser does, so this replaces the anchor-click/Blob trick
     * frontend/js/pywebview_bridge.js uses.
     */
    @JavascriptInterface
    fun saveFile(base64Data: String, contentType: String?, filename: String?) {
        executor.execute {
            try {
                val bytes = Base64.decode(base64Data, Base64.DEFAULT)
                val name = filename?.takeIf { it.isNotBlank() } ?: "download"
                val mime = contentType?.takeIf { it.isNotBlank() } ?: "application/octet-stream"
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    val values = ContentValues().apply {
                        put(MediaStore.MediaColumns.DISPLAY_NAME, name)
                        put(MediaStore.MediaColumns.MIME_TYPE, mime)
                        put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
                    }
                    val uri = context.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                    if (uri == null) {
                        Log.e(TAG, "saveFile: MediaStore insert returned null for $name")
                        return@execute
                    }
                    context.contentResolver.openOutputStream(uri)?.use { it.write(bytes) }
                } else {
                    // Pre-scoped-storage fallback (API 26-28). Requires the
                    // WRITE_EXTERNAL_STORAGE permission (declared in the
                    // manifest with maxSdkVersion=28) to actually be granted —
                    // TODO(Phase 3 hardening): wire the runtime permission
                    // request flow; this path is currently untested.
                    @Suppress("DEPRECATION")
                    val downloadsDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
                    downloadsDir.mkdirs()
                    File(downloadsDir, name).writeBytes(bytes)
                }
            } catch (e: Exception) {
                Log.e(TAG, "saveFile failed for $filename", e)
            }
        }
    }

    /** Flushes the SQLite WAL via the existing exit-snapshot route; called from MainActivity.onStop(). */
    fun flushOnBackground() {
        executor.execute {
            try {
                callApi("POST", "/api/plan/exit-snapshot", null, null)
            } catch (e: Exception) {
                Log.w(TAG, "exit-snapshot on background failed", e)
            }
        }
    }

    private fun deliver(requestId: String, resultJson: String) {
        webView.post {
            webView.evaluateJavascript(
                "window.__androidBridgeResolve && window.__androidBridgeResolve(" +
                    "${JSONObject.quote(requestId)}, ${JSONObject.quote(resultJson)})",
                null
            )
        }
    }
}
