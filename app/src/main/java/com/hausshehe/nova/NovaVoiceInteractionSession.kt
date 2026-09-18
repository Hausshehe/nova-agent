package com.hausshehe.nova

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.service.voice.VoiceInteractionSession
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log
import android.view.View
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView

class NovaVoiceInteractionSession(
    context: Context,
) : VoiceInteractionSession(context) {

    private lateinit var goalInput: EditText
    private lateinit var statusText: TextView
    private var sourcePackage: String? = null
    private var speechRecognizer: SpeechRecognizer? = null

    override fun onCreateContentView(): View {
        val root = LinearLayout(getContext()).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 24, 32, 24)
            setBackgroundColor(Color.BLACK)
        }

        val title = TextView(getContext()).apply {
            text = "Nova"
            textSize = 24f
            setTextColor(Color.WHITE)
            setPadding(0, 0, 0, 12)
        }

        goalInput = EditText(getContext()).apply {
            hint = "Tell Nova what to do"
            setTextColor(Color.WHITE)
            setHintTextColor(0xFFAAAAAA.toInt())
            minLines = 2
            maxLines = 5
        }

        val runButton = Button(getContext()).apply {
            text = "Run"
            setOnClickListener { startGoal() }
        }

        val cancelButton = Button(getContext()).apply {
            text = "Close"
            setOnClickListener { finish() }
        }

        statusText = TextView(getContext()).apply {
            text = "Ready"
            textSize = 14f
            setTextColor(0xFFCCCCCC.toInt())
            setPadding(0, 12, 0, 0)
        }

        root.addView(title)
        root.addView(goalInput, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ))
        root.addView(runButton)
        root.addView(cancelButton)
        root.addView(statusText)

        val listenButton = Button(getContext()).apply {
            text = "Listen"
            setOnClickListener { startListening() }
        }
        root.addView(listenButton)

        return root
    }

    override fun onShow(args: Bundle?, showFlags: Int) {
        super.onShow(args, showFlags)
        sourcePackage = foregroundPackage(args)
        statusText.text = if (sourcePackage.isNullOrBlank()) {
            "Ready"
        } else {
            "Ready to work in " + sourcePackage
        }
        goalInput.requestFocus()
        goalInput.post {
            val imm = getContext().getSystemService(InputMethodManager::class.java)
            imm?.showSoftInput(goalInput, InputMethodManager.SHOW_IMPLICIT)
        }

        if (
            getContext().checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED
        ) {
            startListening()
        }
    }

    override fun onHandleAssist(state: AssistState) {
        if (!state.isFocused) return
        val content = state.assistContent
        Log.i(
            TAG,
            "NOVA_ASSIST_STATE focused=true index=" +
                state.index + "/" + state.count +
                " contentIntent=" + content?.intent?.component,
        )
    }

    override fun onHide() {
        stopListening()
        super.onHide()
        sourcePackage = null
    }

    override fun onDestroy() {
        stopListening()
        sourcePackage = null
        super.onDestroy()
    }

    private fun startListening() {
        if (
            getContext().checkSelfPermission(Manifest.permission.RECORD_AUDIO) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            statusText.text = "Microphone permission is required for voice input"
            return
        }
        if (!SpeechRecognizer.isRecognitionAvailable(getContext())) {
            statusText.text = "No speech recognizer is available"
            return
        }

        stopListening()
        speechRecognizer = SpeechRecognizer.createSpeechRecognizer(getContext()).also { recognizer ->
            recognizer.setRecognitionListener(object : RecognitionListener {
                override fun onReadyForSpeech(params: Bundle?) {
                    statusText.text = "Listening..."
                }

                override fun onBeginningOfSpeech() {
                    statusText.text = "Listening..."
                }

                override fun onRmsChanged(rmsdB: Float) = Unit
                override fun onBufferReceived(buffer: ByteArray?) = Unit

                override fun onEndOfSpeech() {
                    statusText.text = "Processing..."
                }

                override fun onError(error: Int) {
                    statusText.text = "Voice input unavailable. Type the goal instead."
                }

                override fun onResults(results: Bundle?) {
                    val matches = results?.getStringArrayList(
                        SpeechRecognizer.RESULTS_RECOGNITION
                    )
                    val spoken = matches?.firstOrNull()?.trim().orEmpty()
                    if (spoken.isNotBlank()) {
                        goalInput.setText(spoken)
                        goalInput.setSelection(goalInput.text.length)
                        startGoal()
                    } else {
                        statusText.text = "No voice command was detected"
                    }
                }

                override fun onPartialResults(partialResults: Bundle?) = Unit

                override fun onEvent(eventType: Int, params: Bundle?) = Unit
            })

            val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(
                    RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                    RecognizerIntent.LANGUAGE_MODEL_FREE_FORM,
                )
                putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
            }

            try {
                recognizer.startListening(intent)
            } catch (t: Throwable) {
                statusText.text = "Could not start voice input"
                Log.e(TAG, "Speech recognizer start failed", t)
            }
        }
    }

    private fun stopListening() {
        speechRecognizer?.let {
            try {
                it.cancel()
            } catch (_: Throwable) {
            }
            it.destroy()
        }
        speechRecognizer = null
    }

    private fun startGoal() {
        val goal = goalInput.text?.toString()?.trim().orEmpty()
        if (goal.isBlank()) {
            statusText.text = "Enter a goal first"
            return
        }

        val deadlineMs = parseDeadline(goal)
        val taskIntent = NovaTaskService.intent(
            getContext(),
            goal,
            deadlineMs,
            sourcePackage,
        )

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                getContext().startForegroundService(taskIntent)
            } else {
                getContext().startService(taskIntent)
            }

            statusText.text = if (deadlineMs > 0L) {
                deadlineSummary(deadlineMs)
            } else {
                "Started. Nova is working."
            }

            hide()
        } catch (t: Throwable) {
            statusText.text =
                "Could not start task: " + (t.message ?: t.javaClass.simpleName)
            Log.e(TAG, "Unable to start Nova task", t)
        }
    }

    private fun foregroundPackage(args: Bundle?): String? {
        if (Build.VERSION.SDK_INT >= 35 && args != null) {
            val activities = args.getParcelableArrayList<ComponentName>(
                VoiceInteractionSession.KEY_FOREGROUND_ACTIVITIES,
            )
            val focused = activities?.lastOrNull()
            if (focused != null && focused.packageName != getContext().packageName) {
                return focused.packageName
            }
        }

        val intent = args?.getParcelable<Intent>("intent")
        val packageName = intent?.component?.packageName
        if (!packageName.isNullOrBlank() && packageName != getContext().packageName) {
            return packageName
        }

        return null
    }

    private fun parseDeadline(goal: String): Long {
        val match = Regex("""(?i)\bby\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b""")
            .find(goal) ?: return 0L

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

        val target = java.util.Calendar.getInstance().apply {
            set(java.util.Calendar.HOUR_OF_DAY, hour)
            set(java.util.Calendar.MINUTE, minute)
            set(java.util.Calendar.SECOND, 0)
            set(java.util.Calendar.MILLISECOND, 0)
        }
        if (target.timeInMillis <= System.currentTimeMillis()) {
            target.add(java.util.Calendar.DAY_OF_MONTH, 1)
        }
        return target.timeInMillis
    }

    private fun deadlineSummary(deadlineMs: Long): String {
        val time = java.util.Calendar.getInstance().apply {
            timeInMillis = deadlineMs
        }
        val hour = time.get(java.util.Calendar.HOUR)
        val displayHour = if (hour == 0) 12 else hour
        val minute = time.get(java.util.Calendar.MINUTE)
        val marker = if (time.get(java.util.Calendar.AM_PM) == java.util.Calendar.AM) "AM" else "PM"
        return "Started. Deadline " +
            displayHour + ":" + minute.toString().padStart(2, '0') + " " + marker
    }

    private companion object {
        const val TAG = "NovaVoiceSession"
    }
}
