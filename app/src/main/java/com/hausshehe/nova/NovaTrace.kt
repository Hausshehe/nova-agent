package com.hausshehe.nova

import org.json.JSONArray
import org.json.JSONObject
import java.util.LinkedHashMap

object NovaTrace {
    private const val MAX_EVENTS_PER_TASK = 300
    private val traces = LinkedHashMap<String, MutableList<JSONObject>>()

    @Synchronized
    fun record(taskId: String?, source: String, event: String, details: Map<String, Any?> = emptyMap()) {
        val id = taskId?.takeIf { it.isNotBlank() } ?: return
        val events = traces.getOrPut(id) { mutableListOf() }
        val entry = JSONObject().apply {
            put("timestampMs", System.currentTimeMillis())
            put("source", source)
            put("event", event)
            details.forEach { (key, value) -> put(key, value ?: JSONObject.NULL) }
        }
        events.add(entry)
        if (events.size > MAX_EVENTS_PER_TASK) {
            events.removeAt(0)
        }
    }

    @Synchronized
    fun snapshot(taskId: String): JSONArray {
        val result = JSONArray()
        traces[taskId]?.forEach { result.put(JSONObject(it.toString())) }
        return result
    }

    @Synchronized
    fun clear(taskId: String) {
        traces.remove(taskId)
    }
}
