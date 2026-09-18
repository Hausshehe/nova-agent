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
        private const val EXTRA_TASK_ID = "task_id"
        private val executor = Executors.newSingleThreadExecutor()

        fun intent(
            context: Context,
            goal: String,
            deadlineMs: Long,
            sourcePackage: String? = null,
            taskId: String? = null,
        ): Intent =
            Intent(context, NovaTaskService::class.java).apply {
                action = ACTION_START
                putExtra(EXTRA_GOAL, goal)
                putExtra(EXTRA_DEADLINE_MS, deadlineMs)
                if (!sourcePackage.isNullOrBlank()) {
                    putExtra(EXTRA_SOURCE_PACKAGE, sourcePackage)
                }
                if (!taskId.isNullOrBlank()) {
                    putExtra(EXTRA_TASK_ID, taskId)
                }
            }
    }

    private var worker: Future<*>? = null

    override fun onCreate() {
        super.onCreate()
        BridgeServer.start(this)
        createNotificationChannel()
        startForeground(NOTIFICATION_ID, notification("Nova is ready"))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val goal = intent?.getStringExtra(EXTRA_GOAL)?.trim().orEmpty()
        val deadlineMs = intent?.getLongExtra(EXTRA_DEADLINE_MS, 0L) ?: 0L
        val sourcePackage = intent?.getStringExtra(EXTRA_SOURCE_PACKAGE)?.trim().orEmpty()
        val requestedTaskId = intent?.getStringExtra(EXTRA_TASK_ID)?.trim().orEmpty()

        if (goal.isNotBlank()) {
            val existing = TaskStore.get(this)
            if (
                existing != null &&
                existing.status in setOf("running", "pending") &&
                existing.id != requestedTaskId
            ) {
                TaskStore.cancel(this)
                worker?.cancel(true)
                worker = null
            }
            if (requestedTaskId.isNotBlank()) {
                if (TaskStore.get(this)?.id != requestedTaskId) {
                    TaskStore.startNew(this, goal, deadlineMs, requestedTaskId)
                }
            } else {
                TaskStore.startOrResume(this, goal, deadlineMs)
            }
        }

        if (worker?.isDone != false) {
            worker = executor.submit { runActiveTask() }
        }

        return START_STICKY
    }

    private fun runActiveTask() {
        var retryDelayMs = 1000L

        while (!Thread.currentThread().isInterrupted) {
            val task = TaskStore.get(this) ?: return
            if (task.status !in setOf("running", "pending")) return

            if (task.deadlineMs > 0L && System.currentTimeMillis() >= task.deadlineMs) {
                val expired = TaskStore.finish(
                    applicationContext,
                    NovaAgentRunResult(
                        false,
                        task.steps,
                        "task deadline reached before verified completion",
                    ),
                )
                if (expired != null) {
                    updateNotification("Stopped: deadline reached")
                }
                stopSelf()
                return
            }

            updateNotification("Working: " + task.goal.take(60))

            val result = NovaAgentEngine(
                applicationContext,
                sessionId = task.id,
            ).run(
                goal = task.goal,
                deadlineMs = task.deadlineMs,
                shouldStop = {
                    val current = TaskStore.get(applicationContext)
                    current == null ||
                        current.id != task.id ||
                        current.status == "cancelled"
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
                ReasoningSessionRegistry.remove(task.id)
                stopSelf()
                return
            }

            val latest = TaskStore.get(this)
            if (latest == null || latest.id != task.id) {
                return
            }

            if (result.error == "task cancelled" || latest.status == "cancelled") {
                updateNotification("Task cancelled")
                ReasoningSessionRegistry.remove(task.id)
                stopSelf()
                return
            }

            if (
                latest.deadlineMs > 0L &&
                System.currentTimeMillis() >= latest.deadlineMs
            ) {
                TaskStore.finish(applicationContext, result)
                updateNotification("Stopped: deadline reached")
                stopSelf()
                return
            }

            if (latest.deadlineMs == 0L) {
                val failed = TaskStore.finish(applicationContext, result)
                if (failed != null) {
                    updateNotification("Stopped: bounded cycle ended")
                }
                ReasoningSessionRegistry.remove(task.id)
                stopSelf()
                return
            }

            TaskStore.keepRunning(
                applicationContext,
                "bounded cycle ended; fresh observation will drive the next cycle",
            )

            val delay = if (result.steps > 0) {
                retryDelayMs
            } else {
                minOf(retryDelayMs * 2L, 30000L)
            }

            try {
                Thread.sleep(delay)
            } catch (_: InterruptedException) {
                Thread.currentThread().interrupt()
                return
            }

            retryDelayMs = if (result.steps > 0) {
                1000L
            } else {
                minOf(delay * 2L, 30000L)
            }
        }
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
                .setSmallIcon(android.R.drawable.ic_popup_sync)
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
