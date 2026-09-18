package com.hausshehe.nova

import android.app.Activity
import android.Manifest
import android.content.pm.PackageManager
import android.app.role.RoleManager
import android.content.Intent
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import java.util.Calendar

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
    private lateinit var agentGoalInput: EditText
    private lateinit var agentStatus: TextView

    private val statusHandler = Handler(Looper.getMainLooper())
    private val statusPoller = object : Runnable {
        override fun run() {
            updateAgentStatus()
            statusHandler.postDelayed(this, 700L)
        }
    }

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

        content.addView(section("Nova Agent"))
        agentGoalInput = EditText(this).apply {
            hint = "Tell Nova what to do"
            minLines = 2
            maxLines = 5
            setPadding(16, 16, 16, 16)
        }
        content.addView(agentGoalInput, buttonParams())

        content.addView(Button(this).apply {
            text = "Run with DeepSeek"
            contentDescription = "Run with DeepSeek"
            setOnClickListener { runAgentGoal() }
        }, buttonParams())

        content.addView(Button(this).apply {
            text = "Make Nova Assistant"
            contentDescription = "Make Nova Assistant"
            setOnClickListener { requestAssistantRole() }
        }, buttonParams())

        agentStatus = status("Agent idle")
        content.addView(agentStatus)


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
        handleAssistIntent(intent)
    }

    override fun onResume() {
        super.onResume()
        if (::accessibilityStatus.isInitialized) accessibilityStatus.text = accessibilityStatusText()
        statusHandler.post(statusPoller)
    }

    override fun onPause() {
        statusHandler.removeCallbacks(statusPoller)
        super.onPause()
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleAssistIntent(intent)
    }

    private fun handleAssistIntent(intent: Intent?) {
        if (intent?.action != Intent.ACTION_ASSIST || !::agentGoalInput.isInitialized) return
        val text = intent.getStringExtra(Intent.EXTRA_TEXT)?.trim().orEmpty()
        if (text.isNotBlank()) {
            agentGoalInput.setText(text)
            agentGoalInput.setSelection(agentGoalInput.text.length)
            val sourcePackage = intent.getStringExtra(Intent.EXTRA_ASSIST_PACKAGE)
            runAgentGoal(sourcePackage)
            moveTaskToBack(true)
        } else {
            agentGoalInput.requestFocus()
        }
    }

    private fun runAgentGoal(sourcePackage: String? = null) {
        val goal = agentGoalInput.text?.toString()?.trim().orEmpty()
        if (goal.isBlank()) {
            agentStatus.text = "Enter a goal first"
            return
        }

        val deadlineMs = parseDeadline(goal)
        try {
            val taskIntent = NovaTaskService.intent(this, goal, deadlineMs, sourcePackage)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(taskIntent)
            } else {
                startService(taskIntent)
            }
            agentStatus.text = if (deadlineMs > 0L) {
                "Started. Deadline: " + deadlineSummary(deadlineMs)
            } else {
                "Started. DeepSeek is reasoning from the live UI."
            }
        } catch (t: Throwable) {
            agentStatus.text = "Could not start task: " + (t.message ?: t.javaClass.simpleName)
        }
    }

    private fun updateAgentStatus() {
        if (!::agentStatus.isInitialized) return
        val task = TaskStore.get(this)
        agentStatus.text = if (task == null) {
            "Agent idle"
        } else {
            "Task " + task.status +
                " | steps=" + task.steps +
                if (task.lastOutcome.isNotBlank()) " | " + task.lastOutcome else ""
        }
    }

    private fun requestAssistantRole() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M &&
            checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQUEST_AUDIO_PERMISSION)
            agentStatus.text = "Grant microphone access, then tap Make Nova Assistant again"
            return
        }

        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            agentStatus.text = "Assistant role requires Android 10 or newer"
            return
        }
        val roleManager = getSystemService(RoleManager::class.java)
        if (!roleManager.isRoleAvailable(RoleManager.ROLE_ASSISTANT)) {
            agentStatus.text = "This Android build does not expose the assistant role"
            return
        }
        try {
            startActivityForResult(
                roleManager.createRequestRoleIntent(RoleManager.ROLE_ASSISTANT),
                18765,
            )
        } catch (t: Throwable) {
            agentStatus.text = "Unable to request assistant role: " + (t.message ?: t.javaClass.simpleName)
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_AUDIO_PERMISSION) {
            agentStatus.text = if (
                grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED
            ) {
                "Microphone granted. Tap Make Nova Assistant again."
            } else {
                "Microphone denied. Nova can still use typed assistant goals."
            }
        }
    }

    private fun parseDeadline(goal: String): Long {
        val match = Regex("""(?i)\bby\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b""").find(goal)
            ?: return 0L

        val rawHour = match.groupValues[1].toIntOrNull() ?: return 0L
        val minute = match.groupValues[2].toIntOrNull() ?: 0
        val marker = match.groupValues[3].lowercase()
        if (minute !in 0..59) return 0L

        val hour = if (marker.isBlank()) {
            if (rawHour !in 0..23) return 0L
            rawHour
        } else {
            if (rawHour !in 1..12) return 0L
            when {
                marker == "am" && rawHour == 12 -> 0
                marker == "pm" && rawHour != 12 -> rawHour + 12
                else -> rawHour
            }
        }

        val target = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, hour)
            set(Calendar.MINUTE, minute)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
        }
        if (target.timeInMillis <= System.currentTimeMillis()) {
            target.add(Calendar.DAY_OF_MONTH, 1)
        }
        return target.timeInMillis
    }

    private fun deadlineSummary(deadlineMs: Long): String {
        val time = Calendar.getInstance().apply { timeInMillis = deadlineMs }
        val hour = time.get(Calendar.HOUR)
        val displayHour = if (hour == 0) 12 else hour
        val minute = time.get(Calendar.MINUTE)
        val marker = if (time.get(Calendar.AM_PM) == Calendar.AM) "AM" else "PM"
        return displayHour.toString() + ":" + minute.toString().padStart(2, '0') + " " + marker
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

    private companion object {
        const val REQUEST_AUDIO_PERMISSION = 18767
    }

}
