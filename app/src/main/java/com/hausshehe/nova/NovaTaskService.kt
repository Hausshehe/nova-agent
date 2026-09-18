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
        private const val EXTRA_SOURCE_PACKAGE = "source_package"
        private val executor = Executors.newSingleThreadExecutor()

        fun intent(
            context: Context,
            goal: String,
            deadlineMs: Long,
            sourcePackage: String? = null,
        ): Intent =
            Intent(context, NovaTaskService::class.java).apply {
                action = ACTION_START
                putExtra(EXTRA_GOAL, goal)
                putExtra(EXTRA_DEADLINE_MS, deadlineMs)
                if (!sourcePackage.isNullOrBlank()) {
                    putExtra(EXTRA_SOURCE_PACKAGE, sourcePackage)
                }
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
        val sourcePackage = intent?.getStringExtra(EXTRA_SOURCE_PACKAGE)?.trim().orEmpty()

        if (goal.isNotBlank()) {
            val existing = TaskStore.get(this)
            if (
                existing != null &&
                existing.status in setOf("running", "pending") &&
                existing.goal != goal
            ) {
                TaskStore.cancel(this)
                worker?.cancel(true)
                worker = null
            }
            TaskStore.startOrResume(this, goal, deadlineMs)
        }

        if (worker?.isDone != false) {
            worker = executor.submit { runActiveTask() }
        }

        return START_STICKY
    }

    private fun runActiveTask() {
        var cycles = 0
        val maxCycles = 12

        while (cycles < maxCycles) {
            val task = TaskStore.get(this) ?: return
            if (task.status !in setOf("running", "pending")) return

            if (task.deadlineMs > 0L && System.currentTimeMillis() >= task.deadlineMs) {
                val expired = TaskStore.finish(
                    applicationContext,
                    NovaAgentRunResult(false, task.steps, "task deadline reached before verified completion"),
                )
                if (expired != null) {
                    updateNotification("Stopped: deadline reached")
                }
                stopSelf()
                return
            }

            cycles++
            updateNotification("Working: " + task.goal.take(60))

            val result = NovaAgentEngine(applicationContext).run(
                goal = task.goal,
                deadlineMs = task.deadlineMs,
                waitForPackage = sourcePackage.takeIf { it.isNotBlank() },
                shouldStop = {
                    val current = TaskStore.get(applicationContext)
                    current == null || current.id != task.id || current.status == "cancelled"
                },
            ) { progress ->
                val current = TaskStore.get(applicationContext)
                if (current?.id == task.id) {
                    TaskStore.update(applicationContext, progress)
                }
                updateNotification(
                    when (progress.status) {
                        "verified_complete" -> "Goal verified"
                        "invalid_decision" -> "Reassessing current UI"
                        "rejected" -> "Action rejected, reassessing"
                        else -> "Step " + progress.steps + ": " + progress.lastAction.take(48)
                    }
                )
            }

            if (result.success) {
                val completed = TaskStore.finish(applicationContext, result)
                if (completed != null) {
                    updateNotification("Completed: " + completed.goal.take(60))
                }
                stopSelf()
                return
            }

            if (result.error == "task cancelled") {
                val latest = TaskStore.get(this)
                if (latest?.id != task.id) return
                updateNotification("Task cancelled")
                stopSelf()
                return
            }

            val latest = TaskStore.get(this)
            if (latest == null || latest.id != task.id) return
            if (latest.deadlineMs > 0L && System.currentTimeMillis() >= latest.deadlineMs) {
                TaskStore.finish(applicationContext, result)
                updateNotification("Stopped: deadline reached")
                stopSelf()
                return
            }

            if (result.error?.startsWith("step budget exhausted") == true ||
                result.error?.startsWith("DeepSeek reasoning failed") == true
            ) {
                TaskStore.keepRunning(
                    applicationContext,
                    "bounded cycle ended; re-observing current Android state",
                )
                Thread.sleep(500L)
                continue
            }

            val stopped = TaskStore.finish(applicationContext, result)
            if (stopped != null) {
                updateNotification("Stopped: " + (stopped.error ?: "task failed").take(60))
            }
            stopSelf()
            return
        }

        val latest = TaskStore.get(this)
        if (latest != null && latest.status in setOf("running", "pending")) {
            TaskStore.finish(
                applicationContext,
                NovaAgentRunResult(false, latest.steps, "bounded recovery cycles exhausted"),
            )
            updateNotification("Stopped: recovery cycle limit reached")
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
