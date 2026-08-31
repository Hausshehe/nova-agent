package com.hausshehe.nova

import android.content.Context
import android.graphics.Color
import android.view.Gravity
import android.view.ViewGroup
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView

/**
 * Minimal product shell for the rebuilt Nova runtime.
 * Keeps the Android foundation independent from the navigation implementation.
 */
object NovaTaskShell {
    fun create(context: Context, onSubmit: (String) -> Unit): LinearLayout {
        val root = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 48, 32, 32)
            gravity = Gravity.TOP
        }

        root.addView(TextView(context).apply {
            text = "Nova Agent"
            textSize = 28f
        })

        root.addView(TextView(context).apply {
            text = "Goal-driven Android automation"
            textSize = 15f
            setTextColor(Color.GRAY)
        })

        val input = EditText(context).apply {
            hint = "What should Nova do?"
            singleLine = true
            contentDescription = "Nova task input"
        }
        root.addView(input, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { topMargin = 32 })

        root.addView(TextView(context).apply {
            text = "READY"
            textSize = 14f
            contentDescription = "Nova task status"
            setPadding(0, 24, 0, 24)
        })

        root.addView(android.widget.Button(context).apply {
            text = "Run Task"
            contentDescription = "Run Nova task"
            setOnClickListener {
                val goal = input.text.toString().trim()
                if (goal.isNotEmpty()) onSubmit(goal)
            }
        })

        return root
    }
}
