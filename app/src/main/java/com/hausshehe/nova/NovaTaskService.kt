package com.hausshehe.nova

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import java.util.concurrent.Executors
import java.util.concurrent.Future

class NovaTaskService : Service() {
    companion object {
        private const val CHANNEL_ID = "nova_tasks"
        private const val NOTIFICATION_ID = 18766
        private const val ACTION_START = "com.hausshehe.nova.action.START_TASK"
        private const val EXTRA_GOAL = "goal"
        private const val EXTRA_DEADLINE_MS = "deadline_ms"
        private val executor = Executors.newSingleThreadExecutor()

        fun intent(context: Context, goal: String, deadlineMs: Long): Intent =
            Intent(context, NovaTaskService::class.java).apply {
                action = ACTION_START
                putExtra(EXTRA_GOAL, goal)
                putExtra(EXTRA_DEADLINE_MS, deadlineMs)
            }
    }

    private var worker: Future<*>? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(NOTIFICATION_ID, notification("Nova is ready"))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val goal = intent?.getStringExtra(EXTRA_GOAL)?.trim().orEmpty()
        val deadlineMs = intent?.getLongExtra(EXTRA_DEADLINE_MS, 0L) ?: 0L

        if (goal.isNotBlank()) {
            TaskStore.startOrResume(this, goal, deadlineMs)
        }

        if (worker?.isDone != false) {
            worker = executor.submit { runActiveTask() }
        }

        return START_STICKY
    }

    private fun runActiveTask() {
        val task = TaskStore.get(this) ?: return
        if (task.status !in setOf("running", "pending")) return

        updateNotification("Working: " + task.goal.take(60))

        val result = NovaAgentEngine(applicationContext).run(
            goal = task.goal,
            deadlineMs = task.deadlineMs,
        ) { progress ->
            TaskStore.update(applicationContext, progress)
            updateNotification(
                when (progress.status) {
                    "verified_complete" -> "Goal verified"
                    "invalid_decision" -> "Reassessing current UI"
                    "rejected" -> "Action rejected, reassessing"
                    else -> "Step " + progress.steps + ": " + progress.lastAction.take(48)
                }
            )
        }

        val completed = TaskStore.finish(applicationContext, result)
        if (completed != null) {
            updateNotification(
                if (result.success) {
                    "Completed: " + completed.goal.take(60)
                } else {
                    "Stopped: " + (completed.error ?: "task failed").take(60)
                }
            )
        }

        stopSelf()
    }

    override fun onDestroy() {
        worker?.cancel(true)
        worker = null
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun notification(text: String): Notification =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
                .setContentTitle("Nova Agent")
                .setContentText(text)
                .setSmallIcon(android.R.drawable.stat_notify_sync)
                .setOngoing(true)
                .build()
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
                .setContentTitle("Nova Agent")
                .setContentText(text)
                .setSmallIcon(android.R.drawable.stat_notify_sync)
                .setOngoing(true)
                .build()
        }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Nova tasks",
                NotificationManager.IMPORTANCE_LOW,
            )
            getSystemService(NotificationManager::class.java)
                .createNotificationChannel(channel)
        }
    }

    private fun updateNotification(text: String) {
        getSystemService(NotificationManager::class.java)
            .notify(NOTIFICATION_ID, notification(text))
    }
}
