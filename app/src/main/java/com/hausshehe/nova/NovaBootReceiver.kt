package com.hausshehe.nova

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log

class NovaBootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return

        val task = TaskStore.get(context) ?: return
        if (task.status !in setOf("running", "pending")) return
        if (task.deadlineMs > 0L && System.currentTimeMillis() >= task.deadlineMs) return

        val serviceIntent = NovaTaskService.intent(
            context,
            task.goal,
            task.deadlineMs,
        )
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(serviceIntent)
            } else {
                context.startService(serviceIntent)
            }
            Log.i(TAG, "NOVA_BOOT_RESUME_STARTED taskId=" + task.id)
        } catch (t: Throwable) {
            Log.e(TAG, "NOVA_BOOT_RESUME_FAILED", t)
        }
    }

    private companion object {
        const val TAG = "NovaBootReceiver"
    }
}