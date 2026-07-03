package com.retirementsystem.v10

import android.annotation.SuppressLint
import android.net.Uri
import android.os.Bundle
import android.view.KeyEvent
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.webkit.WebViewAssetLoader

/**
 * Single-activity shell: a full-screen WebView loading frontend/index.html
 * (packaged verbatim into assets/frontend, no build step) over
 * WebViewAssetLoader's virtual https://appassets.androidplatform.net/ host,
 * plus the Chaquopy JavascriptInterface bridge frontend/js/android_bridge.js
 * talks to. See documentation/ANDROID_MOBILE_ENHANCEMENT_PLAN.md §4.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var pythonBridge: PythonBridge
    private var filePickerCallback: ValueCallback<Array<Uri>>? = null

    private val filePicker = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        val callback = filePickerCallback
        filePickerCallback = null
        callback?.onReceiveValue(if (uri != null) arrayOf(uri) else null)
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        webView = WebView(this)
        setContentView(webView)

        // Mounted at "/" (not "/frontend/"): AssetsPathHandler resolves the
        // URL suffix *after* the mounted prefix directly against assets/, so
        // requesting .../frontend/index.html here correctly resolves to
        // assets/frontend/index.html (populated by the copyFrontendAssets
        // Gradle task) — mounting at "/frontend/" would instead look for
        // assets/index.html and 404.
        val assetLoader = WebViewAssetLoader.Builder()
            .addPathHandler("/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            // WebView hardening (Phase 3.4): everything the app needs is
            // served by WebViewAssetLoader or crosses the AndroidBridge —
            // the WebView itself gets no filesystem, content-provider, or
            // mixed-content reach. Real file access goes through the
            // OpenDocument picker below; there is no INTERNET permission,
            // so remote loads are dead at the OS layer regardless.
            allowFileAccess = false
            allowContentAccess = false
            mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
            javaScriptCanOpenWindowsAutomatically = false
            setSupportMultipleWindows(false)
        }

        pythonBridge = PythonBridge(this, webView)
        webView.addJavascriptInterface(pythonBridge, "AndroidBridge")

        webView.webViewClient = object : WebViewClient() {
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
                return assetLoader.shouldInterceptRequest(request.url)
            }

            // Navigation lockdown (Phase 3.4): the WebView may only ever
            // display the bundled frontend. Any other target — a remote URL
            // in imported/plan-entered text, file://, intent:// — is
            // swallowed rather than navigated to. (With no INTERNET
            // permission remote loads would fail anyway; this keeps the
            // failure silent and the app on-page instead of showing a
            // WebView error page.)
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                return request.url.host != "appassets.androidplatform.net"
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            // Backs every <input type=file> in the frontend (YTD CSV import,
            // saved-plan .rpx import) — the existing routes are unchanged,
            // only how the browser chrome hands back a picked file differs.
            override fun onShowFileChooser(
                view: WebView,
                callback: ValueCallback<Array<Uri>>,
                params: FileChooserParams
            ): Boolean {
                filePickerCallback?.onReceiveValue(null)
                filePickerCallback = callback
                return try {
                    filePicker.launch(arrayOf("*/*"))
                    true
                } catch (e: Exception) {
                    filePickerCallback = null
                    false
                }
            }
        }

        webView.loadUrl("https://appassets.androidplatform.net/frontend/index.html")
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (keyCode == KeyEvent.KEYCODE_BACK && webView.canGoBack()) {
            webView.goBack()
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    override fun onStop() {
        super.onStop()
        // Mirrors the desktop exitApp()/on_closing() flow (src/desktop_app.py):
        // checkpoint the SQLite WAL whenever the app leaves the foreground,
        // since Android can kill a backgrounded process without warning.
        pythonBridge.flushOnBackground()
    }
}
