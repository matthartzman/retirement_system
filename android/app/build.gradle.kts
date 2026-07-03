import java.io.File

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

// Single source of truth for the version string is src/version.py (shared with
// the desktop build) — read it instead of hand-duplicating a number here.
val versionPyText = File(rootDir, "../src/version.py").readText()
val pyVersion = Regex("VERSION\\s*=\\s*'([^']+)'").find(versionPyText)?.groupValues?.get(1) ?: "10"

android {
    namespace = "com.retirementsystem.v10"
    compileSdk = 34
    ndkVersion = "26.1.10909125"

    defaultConfig {
        applicationId = "com.retirementsystem.v10"
        // minSdk 26 (Android 8.0): matches the plan's Acceptance Criteria (§8.1)
        // and is Chaquopy's floor for a modern Python 3.11 build.
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = pyVersion
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        ndk {
            // arm64 is the primary target (§7 risk: APK size); add x86_64 for
            // the emulator. See documentation/ANDROID_MOBILE_ENHANCEMENT_PLAN.md 3.2.
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    // Per-ABI APKs (Phase 3.2): numpy/matplotlib native wheels dominate APK
    // size, and shipping both ABIs in one APK roughly doubles it. The arm64
    // APK is the one that gets sideloaded to a real phone; x86_64 exists only
    // for the emulator. No universal APK — there is no store requiring one.
    splits {
        abi {
            isEnable = true
            reset()
            include("arm64-v8a", "x86_64")
            isUniversalApk = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }

    // frontend/ has no build step of its own (see documentation/CLAUDE.md);
    // it is loaded byte-for-byte, the same as the PyWebView desktop shell does.
    sourceSets["main"].assets.srcDir("src/main/assets")
}

chaquopy {
    defaultConfig {
        version = "3.11"
        pip {
            // Mirrors the "Core (all platforms)" group in requirements.txt —
            // pywebview is deliberately omitted; the native WebView shell
            // replaces it entirely on Android.
            install("numpy>=1.26,<3")
            install("openpyxl>=3.1,<4")
            install("reportlab>=4.0,<5")
            install("matplotlib>=3.8,<4")
            install("pillow>=10,<12")
            install("cryptography>=42,<46")
        }
    }
    sourceSets {
        getByName("main") {
            // Root the source set at the repo root (not src/ directly) so the
            // extracted layout keeps "src" as a real importable package —
            // `from src.server import create_app` (used throughout src/)
            // requires a "src" directory to exist above app_core.py, not just
            // its contents flattened to the python path root.
            //
            // reference_data/ and system_config.csv ride along because
            // src/server/app_core.py's BASE_DIR (= its own __file__.parents[2])
            // expects them as siblings of src/ — same layout as the desktop
            // checkout. tools/ is deliberately excluded: the subprocess build
            // path that uses it never runs on Android (platform_runtime picks
            // the in-process BuildRunner once android_api.configure() marks
            // the platform as mobile).
            srcDir(File(rootDir, "..").canonicalPath)
            include("src/**", "reference_data/**", "system_config.csv")
        }
    }
}

// The frontend has no build step — copy it verbatim into assets so
// WebViewAssetLoader can serve it, same bytes PyWebView loads from disk.
// Desktop-only test/tooling files are not needed on-device and are excluded.
tasks.register<Copy>("copyFrontendAssets") {
    from(File(rootDir, "../frontend"))
    into("src/main/assets/frontend")
    exclude("**/*.pyc", "**/__pycache__/**")
}

tasks.named("preBuild") {
    dependsOn("copyFrontendAssets")
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.webkit:webkit:1.11.0")
    implementation("androidx.activity:activity-ktx:1.9.1")

    // On-device smoke test (Phase 3.6) — see androidTest/GoldenPathSmokeTest.kt.
    androidTestImplementation("androidx.test:core-ktx:1.6.1")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
}
