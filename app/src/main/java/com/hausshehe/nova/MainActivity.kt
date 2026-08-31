package com.hausshehe.nova

import android.app.Activity
import android.os.Bundle
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

class MainActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        BridgeServer.start(applicationContext)

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 48, 32, 32)
        }

        root.addView(TextView(this).apply {
            text = "Nova Agent"
            textSize = 24f
        })

        root.addView(Button(this).apply {
            id = R.id.test_navigation_action
            text = "Test Navigation Action"
            contentDescription = "Test Navigation Action"
            setOnClickListener {
                text = "Navigation Action Completed"
            }
        })

        setContentView(root)
    }
}
