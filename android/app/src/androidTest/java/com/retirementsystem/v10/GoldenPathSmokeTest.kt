package com.retirementsystem.v10

import android.webkit.WebView
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * On-device smoke test (Android plan, Phase 3.6): boots the real activity —
 * embedded CPython, route registry, WebView, bridge and all — and asserts the
 * frontend actually arrived and can reach Python over the AndroidBridge.
 *
 * Scaffold status: written alongside Phase 3 but not yet executed (authored
 * without an emulator). Run with `gradle -p android :app:connectedDebugAndroidTest`
 * against an emulator/device; the plan's §3.6 follow-on is wiring this into CI
 * with an emulator action once the plain build workflow is proven out.
 */
@RunWith(AndroidJUnit4::class)
class GoldenPathSmokeTest {

    private fun evalJs(webView: WebView, script: String, timeoutSeconds: Long = 30): String {
        val latch = CountDownLatch(1)
        var result = ""
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            webView.evaluateJavascript(script) { value ->
                result = value ?: "null"
                latch.countDown()
            }
        }
        assertTrue("evaluateJavascript timed out: $script", latch.await(timeoutSeconds, TimeUnit.SECONDS))
        return result
    }

    @Test
    fun frontendLoadsAndBridgeReachesPython() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            var webView: WebView? = null
            scenario.onActivity { activity ->
                webView = activity.findViewById(android.R.id.content)
                    ?.let { root -> (root as android.view.ViewGroup).getChildAt(0) as? WebView }
            }
            val wv = requireNotNull(webView) { "MainActivity did not mount a WebView" }

            // Poll until the SPA has booted (dashboard.js defines setStep).
            val deadline = System.currentTimeMillis() + 60_000
            var booted = false
            while (System.currentTimeMillis() < deadline && !booted) {
                booted = evalJs(wv, "typeof window.setStep === 'function' && !!window.AndroidBridge") == "true"
                if (!booted) Thread.sleep(1_000)
            }
            assertTrue("frontend never finished booting inside the WebView", booted)

            // Round-trip a real API call through JS -> Kotlin -> Chaquopy ->
            // route registry and back. /api/runtime is cheap and always on.
            val probe = """
                (function () {
                  window.__smokeProbe = 'pending';
                  fetch('/api/runtime').then(function (r) { return r.json(); }).then(function (d) {
                    window.__smokeProbe = (d && d.success !== false) ? 'ok' : 'failed';
                  }).catch(function () { window.__smokeProbe = 'failed'; });
                  return true;
                })()
            """.trimIndent()
            evalJs(wv, probe)
            var outcome = "pending"
            val apiDeadline = System.currentTimeMillis() + 60_000
            while (System.currentTimeMillis() < apiDeadline && outcome == "\"pending\"".trim('"')) {
                Thread.sleep(500)
                outcome = evalJs(wv, "window.__smokeProbe").trim('"')
            }
            assertEquals("bridge round-trip to the Python route registry failed", "ok", outcome)
        }
    }
}
