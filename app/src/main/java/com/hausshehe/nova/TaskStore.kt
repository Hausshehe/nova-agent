package com.hausshehe.nova

import android.content.Context
import org.json.JSONObject
import java.util.UUID

data class NovaTaskSnapshot(
    val id: String,
    val goal: String,
    val deadlineMs: Long,
    val status: String,
    val steps: Int,
    val observationId: Long,
    val lastAction: String,
    val lastOutcome: String,
    val error: String?,
    val startedAtMs: Long,
    val updatedAtMs: Long,
)

object TaskStore {
    private const val PREFS = "nova_task_store"
    private const val KEY_TASK = "active_task"

    @Synchronized
    fun startOrResume(context: Context, goal: String, deadlineMs: Long): NovaTaskSnapshot {
        get(context)?.let { existing ->
            if (existing.goal == goal && existing.status in setOf("running", "pending")) {
                return existing
            }
        }

        val now = System.currentTimeMillis()
        return NovaTaskSnapshot(
            id = UUID.randomUUID().toString(),
            goal = goal,
            deadlineMs = deadlineMs,
            status = "running",
            steps = 0,
            observationId = 0L,
            lastAction = "",
            lastOutcome = "task started",
            error = null,
            startedAtMs = now,
            updatedAtMs = now,
        ).also { save(context, it) }
    }

    @Synchronized
    fun get(context: Context): NovaTaskSnapshot? {
        val raw = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_TASK, null) ?: return null

        return try {
            val json = JSONObject(raw)
            NovaTaskSnapshot(
                id = json.getString("id"),
                goal = json.getString("goal"),
                deadlineMs = json.optLong("deadlineMs", 0L),
                status = json.optString("status", "running"),
                steps = json.optInt("steps", 0),
                observationId = json.optLong("observationId", 0L),
                lastAction = json.optString("lastAction", ""),
                lastOutcome = json.optString("lastOutcome", ""),
                error = json.optString("error", "").ifBlank { null },
                startedAtMs = json.optLong("startedAtMs", 0L),
                updatedAtMs = json.optLong("updatedAtMs", 0L),
            )
        } catch (_: Throwable) {
            null
        }
    }

    @Synchronized
    fun update(context: Context, progress: NovaAgentProgress): NovaTaskSnapshot? {
        val existing = get(context) ?: return null
        return existing.copy(
            status = progress.status,
            steps = progress.steps,
            observationId = progress.observationId,
            lastAction = progress.lastAction,
            lastOutcome = progress.lastOutcome,
            error = progress.error,
            updatedAtMs = System.currentTimeMillis(),
        ).also { save(context, it) }
    }

    @Synchronized
    fun keepRunning(context: Context, outcome: String): NovaTaskSnapshot? {
        val existing = get(context) ?: return null
        return existing.copy(
            status = "running",
            lastOutcome = outcome,
            error = null,
            updatedAtMs = System.currentTimeMillis(),
        ).also { save(context, it) }
    }

    @Synchronized
    fun finish(context: Context, result: NovaAgentRunResult): NovaTaskSnapshot? {
        val existing = get(context) ?: return null
        return existing.copy(
            status = if (result.success) "succeeded" else "failed",
            steps = result.steps,
            error = result.error,
            lastOutcome = if (result.success) "verified goal completion" else (result.error ?: "task failed"),
            updatedAtMs = System.currentTimeMillis(),
        ).also { save(context, it) }
    }

    @Synchronized
    fun cancel(context: Context): NovaTaskSnapshot? {
        val existing = get(context) ?: return null
        return existing.copy(
            status = "cancelled",
            lastOutcome = "task cancelled",
            updatedAtMs = System.currentTimeMillis(),
        ).also { save(context, it) }
    }

    fun snapshotJson(context: Context): JSONObject {
        val task = get(context)
        if (task == null) return JSONObject().put("task", JSONObject.NULL)

        return JSONObject().apply {
            put("id", task.id)
            put("goal", task.goal)
            put("deadlineMs", task.deadlineMs)
            put("status", task.status)
            put("steps", task.steps)
            put("observationId", task.observationId)
            put("lastAction", task.lastAction)
            put("lastOutcome", task.lastOutcome)
            put("error", task.error ?: JSONObject.NULL)
            put("startedAtMs", task.startedAtMs)
            put("updatedAtMs", task.updatedAtMs)
        }
    }

    private fun save(context: Context, task: NovaTaskSnapshot) {
        val json = snapshot(task)
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_TASK, json.toString())
            .apply()
    }

    private fun snapshot(task: NovaTaskSnapshot): JSONObject =
        JSONObject().apply {
            put("id", task.id)
            put("goal", task.goal)
            put("deadlineMs", task.deadlineMs)
            put("status", task.status)
            put("steps", task.steps)
            put("observationId", task.observationId)
            put("lastAction", task.lastAction)
            put("lastOutcome", task.lastOutcome)
            put("error", task.error ?: JSONObject.NULL)
            put("startedAtMs", task.startedAtMs)
            put("updatedAtMs", task.updatedAtMs)
        }
}
