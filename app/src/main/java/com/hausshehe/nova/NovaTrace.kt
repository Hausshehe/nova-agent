package com.hausshehe.nova

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.LinkedHashMap

object NovaTrace {
    private const val MAX_EVENTS_PER_TASK = 300
    private const val TRACE_DIRECTORY = "nova-traces"
    private val traces = LinkedHashMap<String, MutableList<JSONObject>>()
    private var traceDirectory: File? = null

    @Synchronized
    fun initialize(context: Context) {
        traceDirectory = File(context.applicationContext.filesDir, TRACE_DIRECTORY).also { it.mkdirs() }
    }

    @Synchronized
    fun record(taskId: String?, source: String, event: String, details: Map<String, Any?> = emptyMap()) {
        val id = taskId?.takeIf { it.isNotBlank() } ?: return
        val entry = JSONObject().apply {
            put("timestampMs", System.currentTimeMillis())
            put("source", source)
            put("event", event)
            details.forEach { (key, value) -> put(key, value ?: JSONObject.NULL) }
        }

        val events = traces.getOrPut(id) { loadFromDisk(id).toMutableList() }
        events.add(entry)
        while (events.size > MAX_EVENTS_PER_TASK) {
            events.removeAt(0)
        }
        persist(id, events)
    }

    @Synchronized
    fun snapshot(taskId: String): JSONArray {
        val events = traces[taskId] ?: loadFromDisk(taskId).also {
            traces[taskId] = it.toMutableList()
        }
        return JSONArray().also { result ->
            events.forEach { result.put(JSONObject(it.toString())) }
        }
    }

    @Synchronized
    fun clear(taskId: String) {
        traces.remove(taskId)
        traceFile(taskId)?.delete()
    }

    private fun loadFromDisk(taskId: String): List<JSONObject> {
        val file = traceFile(taskId) ?: return emptyList()
        if (!file.exists()) return emptyList()
        return file.readLines()
            .filter { it.isNotBlank() }
            .takeLast(MAX_EVENTS_PER_TASK)
            .mapNotNull { line ->
                runCatching { JSONObject(line) }.getOrNull()
            }
    }

    private fun persist(taskId: String, events: List<JSONObject>) {
        val file = traceFile(taskId) ?: return
        file.parentFile?.mkdirs()
        file.writeText(events.joinToString("\n") { it.toString() } + if (events.isNotEmpty()) "\n" else "")
    }

    private fun traceFile(taskId: String): File? {
        val directory = traceDirectory ?: return null
        val safeId = taskId.replace(Regex("[^A-Za-z0-9._-]"), "_")
        return File(directory, "$safeId.jsonl")
    }
}
