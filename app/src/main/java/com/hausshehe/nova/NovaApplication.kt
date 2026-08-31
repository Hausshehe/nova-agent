package com.hausshehe.nova

import android.app.Application

class NovaApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        BridgeServer.start(this)
    }
}
