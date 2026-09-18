package com.hausshehe.nova

import android.app.Application

class NovaApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        NovaTrace.initialize(this)
        BridgeServer.start(this)
    }
}
