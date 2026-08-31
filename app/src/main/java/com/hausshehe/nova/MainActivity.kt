package com.hausshehe.nova

import android.app.Activity
import android.os.Bundle

class MainActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        BridgeServer.start(applicationContext)

        setContentView(NovaTaskShell.create(this) { goal ->
            // R1.5 only establishes the product shell. Task execution remains owned
            // by the existing runtime/navigation path until the next verified layer.
        })
    }
}
