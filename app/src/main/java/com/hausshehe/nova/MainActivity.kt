package com.hausshehe.nova

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.provider.Settings
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

class MainActivity : Activity() {
    private var navigationClicks = 0
    private var recoveryRuns = 0
    private var multiStepRuns = 0
    private var multiStepStep = 0

    private lateinit var navigationStatus: TextView
    private lateinit var recoveryStatus: TextView
    private lateinit var multiStepStatus: TextView
    private lateinit var accessibilityStatus: TextView
    private lateinit var continueButton: Button
    private lateinit var finishButton: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        startService(Intent(this, BridgeHostService::class.java))

        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 48, 32, 32)
        }
        val root = ScrollView(this).apply {
            addView(content, ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ))
        }

        content.addView(TextView(this).apply { text = "Nova Agent"; textSize = 26f })
        content.addView(TextView(this).apply {
            text = "Android navigation test harness"
            textSize = 15f
            setTextColor(Color.GRAY)
            setPadding(0, 8, 0, 24)
        })

        // Keep the recovery controls near the top of the harness. Accessibility
        // services on some Android builds can omit off-screen ScrollView
        // descendants after a focused click. The replanning smoke needs both
        // the failed primary and fallback targets to remain observable while
        // testing accepted-but-unchanged actions.
        content.addView(section("Recovery"))
        val recoveryButton = Button(this).apply {
            id = R.id.recovery_test
            text = "Recovery Test"
            contentDescription = "Recovery Test"
            setOnClickListener {
                recoveryRuns++
                recoveryStatus.text = "Recovery run $recoveryRuns: choose a recovery action"
            }
        }
        content.addView(recoveryButton, buttonParams())
        val recoveryPrimary = Button(this).apply {
            id = R.id.recovery_primary
            text = "Recovery Primary Action"
            contentDescription = "Recovery Primary Action"
            setOnClickListener { recoveryStatus.text = "Primary action failed. Recovery required." }
        }
        content.addView(recoveryPrimary, buttonParams())
        val recoveryFallback = Button(this).apply {
            id = R.id.recovery_fallback
            text = "Recovery Fallback Action"
            contentDescription = "Recovery Fallback Action"
            setOnClickListener { recoveryStatus.text = "Recovery completed" }
        }
        content.addView(recoveryFallback, buttonParams())
        recoveryStatus = status("Recovery ready")
        content.addView(recoveryStatus)

        content.addView(section("Accessibility"))
        accessibilityStatus = status(accessibilityStatusText())
        content.addView(accessibilityStatus)
        content.addView(Button(this).apply {
            text = "Open Accessibility Settings"
            contentDescription = "Open Accessibility Settings"
            setOnClickListener { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }
        }, buttonParams())

        content.addView(section("Navigation"))
        val navigationButton = Button(this).apply {
            id = R.id.test_navigation_action
            text = "Test Navigation Action"
            contentDescription = "Test Navigation Action"
            setOnClickListener {
                navigationClicks++
                text = "Navigation Action Completed"
                navigationStatus.text = "Clicked $navigationClicks time${if (navigationClicks == 1) "" else "s"}"
            }
        }
        content.addView(navigationButton, buttonParams())
        navigationStatus = status("Clicked 0 times")
        content.addView(navigationStatus)

        content.addView(section("Multi-Step"))
        val multiStepButton = Button(this).apply {
            id = R.id.multi_step_test
            text = "Multi-Step Test"
            contentDescription = "Multi-Step Test"
            setOnClickListener {
                multiStepRuns++
                multiStepStep = 1
                multiStepStatus.text = "Run $multiStepRuns: Step 1 started"
                updateMultiStepAffordances()
            }
        }
        content.addView(multiStepButton, buttonParams())
        continueButton = Button(this).apply {
            id = R.id.multi_step_continue
            text = "Continue Multi-Step"
            contentDescription = "Continue Multi-Step"
            isEnabled = false
            setOnClickListener {
                if (multiStepStep == 1) {
                    multiStepStep = 2
                    multiStepStatus.text = "Step 2 started"
                    updateMultiStepAffordances()
                }
            }
        }
        content.addView(continueButton, buttonParams())
        finishButton = Button(this).apply {
            id = R.id.multi_step_finish
            text = "Finish Multi-Step"
            contentDescription = "Finish Multi-Step"
            isEnabled = false
            setOnClickListener {
                if (multiStepStep == 2) {
                    multiStepStep = 3
                    multiStepStatus.text = "Multi-Step Test completed"
                    updateMultiStepAffordances()
                }
            }
        }
        content.addView(finishButton, buttonParams())
        multiStepStatus = status("Multi-Step ready")
        content.addView(multiStepStatus)

        setContentView(root)
    }

    override fun onResume() {
        super.onResume()
        if (::accessibilityStatus.isInitialized) accessibilityStatus.text = accessibilityStatusText()
    }

    private fun accessibilityStatusText(): String =
        if (NovaAccessibilityService.instance != null) "Accessibility service connected"
        else "Accessibility service is not connected"

    private fun updateMultiStepAffordances() {
        if (!::continueButton.isInitialized || !::finishButton.isInitialized) return
        continueButton.isEnabled = multiStepStep == 1
        finishButton.isEnabled = multiStepStep == 2
    }

    private fun section(title: String): TextView = TextView(this).apply {
        text = title
        textSize = 18f
        setPadding(0, 20, 0, 4)
    }

    private fun status(textValue: String): TextView = TextView(this).apply {
        text = textValue
        textSize = 14f
        setTextColor(Color.DKGRAY)
        setPadding(0, 2, 0, 8)
    }

    private fun buttonParams() = LinearLayout.LayoutParams(
        ViewGroup.LayoutParams.MATCH_PARENT,
        ViewGroup.LayoutParams.WRAP_CONTENT
    )
}
