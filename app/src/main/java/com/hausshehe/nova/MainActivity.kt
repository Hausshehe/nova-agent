package com.hausshehe.nova

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

class MainActivity : Activity() {
    private var navigationClicks = 0
    private var recoveryRuns = 0
    private var multiStepRuns = 0
    private var multiStepStep = 0

    private lateinit var navigationStatus: TextView
    private lateinit var recoveryStatus: TextView
    private lateinit var multiStepStatus: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        startService(Intent(this, BridgeHostService::class.java))

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 48, 32, 32)
        }

        root.addView(TextView(this).apply {
            text = "Nova Agent"
            textSize = 26f
        })

        root.addView(TextView(this).apply {
            text = "Android navigation test harness"
            textSize = 15f
            setTextColor(Color.GRAY)
            setPadding(0, 8, 0, 24)
        })

        root.addView(section("Navigation"))
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
        root.addView(navigationButton, buttonParams())

        navigationStatus = status("Clicked 0 times")
        root.addView(navigationStatus)

        root.addView(section("Recovery"))
        val recoveryButton = Button(this).apply {
            id = R.id.recovery_test
            text = "Recovery Test"
            contentDescription = "Recovery Test"
            setOnClickListener {
                recoveryRuns++
                recoveryStatus.text = "Recovery run $recoveryRuns: choose a recovery action"
            }
        }
        root.addView(recoveryButton, buttonParams())

        val recoveryPrimary = Button(this).apply {
            id = R.id.recovery_primary
            text = "Recovery Primary Action"
            contentDescription = "Recovery Primary Action"
            setOnClickListener {
                recoveryStatus.text = "Primary action failed. Recovery required."
            }
        }
        root.addView(recoveryPrimary, buttonParams())

        val recoveryFallback = Button(this).apply {
            id = R.id.recovery_fallback
            text = "Recovery Fallback Action"
            contentDescription = "Recovery Fallback Action"
            setOnClickListener {
                recoveryStatus.text = "Recovery completed"
            }
        }
        root.addView(recoveryFallback, buttonParams())

        recoveryStatus = status("Recovery ready")
        root.addView(recoveryStatus)

        root.addView(section("Multi-Step"))
        val multiStepButton = Button(this).apply {
            id = R.id.multi_step_test
            text = "Multi-Step Test"
            contentDescription = "Multi-Step Test"
            setOnClickListener {
                multiStepRuns++
                multiStepStep = 1
                multiStepStatus.text = "Run $multiStepRuns: Step 1 started"
            }
        }
        root.addView(multiStepButton, buttonParams())

        val continueButton = Button(this).apply {
            id = R.id.multi_step_continue
            text = "Continue Multi-Step"
            contentDescription = "Continue Multi-Step"
            setOnClickListener {
                if (multiStepStep == 1) {
                    multiStepStep = 2
                    multiStepStatus.text = "Step 2 started"
                } else {
                    multiStepStatus.text = "Start a Multi-Step Test first"
                }
            }
        }
        root.addView(continueButton, buttonParams())

        val finishButton = Button(this).apply {
            id = R.id.multi_step_finish
            text = "Finish Multi-Step"
            contentDescription = "Finish Multi-Step"
            setOnClickListener {
                if (multiStepStep == 2) {
                    multiStepStep = 3
                    multiStepStatus.text = "Multi-Step Test completed"
                } else {
                    multiStepStatus.text = "Complete the previous steps first"
                }
            }
        }
        root.addView(finishButton, buttonParams())

        multiStepStatus = status("Multi-Step ready")
        root.addView(multiStepStatus)

        root.addView(section("Stale Transition Safety"))
        val staleStatus = status("Stale safety ready")
        root.addView(staleStatus)

        val staleTarget = Button(this).apply {
            id = R.id.stale_target
            text = "Stale Target"
            contentDescription = "Stale Target"
            setOnClickListener {
                throw IllegalStateException("stale target was physically executed")
            }
        }
        root.addView(staleTarget, buttonParams())

        val staleFreshTarget = Button(this).apply {
            id = R.id.stale_fresh_target
            text = "Fresh Target"
            contentDescription = "Fresh Target"
            visibility = View.GONE
            setOnClickListener {
                staleStatus.text = "Stale transition safety completed"
            }
        }
        root.addView(staleFreshTarget, buttonParams())

        val invalidateStale = Button(this).apply {
            id = R.id.stale_invalidate
            text = "Invalidate Stale Target"
            contentDescription = "Invalidate Stale Target"
            setOnClickListener {
                staleTarget.visibility = View.GONE
                staleFreshTarget.visibility = View.VISIBLE
                staleStatus.text = "Old target invalidated. Choose fresh target."
            }
        }
        root.addView(invalidateStale, buttonParams())

        val staleTest = Button(this).apply {
            id = R.id.stale_test
            text = "Stale Safety Test"
            contentDescription = "Stale Safety Test"
            setOnClickListener {
                staleTarget.visibility = View.VISIBLE
                staleFreshTarget.visibility = View.GONE
                staleStatus.text = "Stale target available"
            }
        }
        root.addView(staleTest, buttonParams())

        setContentView(root)
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
