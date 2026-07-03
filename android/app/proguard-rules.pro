# Release builds ship with isMinifyEnabled = false for now (see build.gradle.kts) —
# Chaquopy's embedded interpreter and reflection-based JavascriptInterface calls
# need care under R8/ProGuard that hasn't been validated yet (Phase 3 hardening).
# This file is a placeholder for those rules once minification is turned on.
