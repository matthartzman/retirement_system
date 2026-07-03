package com.retirementsystem.v10

import android.app.Application
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

/**
 * Starts the embedded CPython interpreter once for the app's whole process
 * lifetime. [MainActivity] (and any future activity) shares this single
 * interpreter instance via [Python.getInstance].
 */
class RetirementApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }
    }
}
