// Top-level build file — declares plugin versions once so app/build.gradle.kts
// can apply them without repeating a version number (avoids drift between the
// classpath and the applied-plugin version).
plugins {
    id("com.android.application") version "8.5.2" apply false
    id("org.jetbrains.kotlin.android") version "1.9.24" apply false
    id("com.chaquo.python") version "16.0.0" apply false
}
