package com.hausshehe.nova

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.util.Log
import android.view.accessibility.AccessibilityNodeInfo
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.PrintWriter
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.Executors

object BridgeServer {
    private const val TAG = "NovaBridgeServer"
    private const val PORT = 18765
    private const val DEEPSEEK_NATIVE_PORT = 18766
    private const val PACKAGE = "com.hausshehe.nova"
    private const val START_RETRIES = 20
    private const val RETRY_DELAY_MS = 250L
    private const val LAUNCH_WAIT_MS = 3000L
    private const val OBSERVATION_POLL_MS = 100L
    private const val ACTION_CHANGE_TIMEOUT_MS = 2000L
    private const val DEEPSEEK_CONNECT_TIMEOUT_MS = 1000
    private const val DEEPSEEK_READ_TIMEOUT_MS = 3000
    private const val DEEPSEEK_RESPONSE_TIMEOUT_MS = 30000L
    private const val DEEPSEEK_BOOTSTRAP_WAIT_MS = 5000L
    private const val DEEPSEEK_BOOTSTRAP_POLL_MS = 250L
    private val executor = Executors.newCachedThreadPool()
    private val deepSeekResponseLock = Object()
    private var deepSeekResponseActive = false
    private var deepSeekResponseFinished = false
    private var deepSeekResponseText = ""
    private var deepSeekResponseError: String? = null
    @Volatile private var started = false

    @Synchronized
    fun start(context: Context) {
        if (started) return
        started = true
        executor.execute { serve(context.applicationContext) }
    }

    private fun serve(context: Context) {
        var server: ServerSocket? = null
        try {
            for (attempt in 1..START_RETRIES) {
                try {
                    server = ServerSocket(PORT, 50, InetAddress.getByName("127.0.0.1"))
                    break
                } catch (e: Exception) {
                    Log.e(TAG, "Bridge bind failed ($attempt/$START_RETRIES): ${e.message}", e)
                    if (attempt < START_RETRIES) Thread.sleep(RETRY_DELAY_MS)
                }
            }
            val listeningServer = server ?: return
            listeningServer.use { boundServer ->
                while (true) {
                    val socket = boundServer.accept()
                    executor.execute { handle(context, socket) }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Bridge server stopped: ${e.message}", e)
        } finally {
            server?.takeIf { !it.isClosed }?.close()
            started = false
        }
    }

    private fun handle(context: Context, socket: Socket) {
        socket.use { s ->
            try {
                val reader = BufferedReader(InputStreamReader(s.getInputStream()))
                val writer = PrintWriter(s.getOutputStream(), true)
                val requestLine = reader.readLine() ?: return
                val request = JSONObject(requestLine)
                val command = request.optString("command")
                Log.i(
                    TAG,
                    "BRIDGE_COMMAND_RECEIVED command=" + command +
                        " thread=" + Thread.currentThread().name +
                        " remote=" + s.inetAddress?.hostAddress + ":" + s.port
                )
                val response = when (command) {
                    "observe" -> observe()
                    "health" -> health()
                    "deepseek_event" -> deepSeekEvent(request)
                    "deepseek_native_prompt" -> deepSeekNativePrompt(context, request)
                    "agent_goal" -> agentGoal(context, request)
                    "agent_status" -> agentStatus(context)
                    "agent_trace" -> agentTrace(context, request)
                    "agent_deepseek_trace" -> agentDeepSeekTrace(context, request)
                    "agent_result" -> agentResult(context, request)
                    "agent_cancel" -> agentCancel(context)
                    "click" -> click(request.optString("elementId"))
                    "scroll" -> scroll(request.optString("elementId"))
                    "back" -> back()
                    "launch" -> launch(context, request.optString("package", PACKAGE))
                    "open_uri" -> openUri(context, request.optString("uri"), request.optString("package").takeIf { it.isNotBlank() })
                    "share_text" -> shareText(
                        context,
                        request.optString("text"),
                        request.optString("package"),
                        request.optString("component"),
                    )
                    else -> error("unknown command: ${request.optString("command")}")
                }
                writer.println(response.toString())
            } catch (e: Exception) {
                Log.e(TAG, "Bridge request failed: ${e.message}", e)
                PrintWriter(s.getOutputStream(), true).println(error(e.message ?: "bridge error").toString())
            }
        }
    }

    private fun deepSeekEvent(request: JSONObject): JSONObject {
        val event = request.optString("event")
        val type = request.optString("type")
        val id = request.optInt("id", -1)
        val delta = request.optString("delta", "")
        val text = request.optString("text", "")
        synchronized(deepSeekResponseLock) {
            if (deepSeekResponseActive) {
                when (event) {
                    "started" -> {
                        deepSeekResponseText = ""
                        deepSeekResponseFinished = false
                        deepSeekResponseError = null
                    }
                    "delta" -> deepSeekResponseText += delta
                    "replaced" -> deepSeekResponseText = text
                    "finished" -> {
                        if (text.isNotEmpty()) deepSeekResponseText = text
                        deepSeekResponseFinished = true
                        deepSeekResponseLock.notifyAll()
                    }
                }
            }
        }
        Log.i(
            TAG,
            "DEEPSEEK_BRIDGE_EVENT event=$event type=$type id=$id " +
                "deltaLength=${delta.length} textLength=${text.length}"
        )
        return JSONObject().apply {
            put("ok", true)
            put("accepted", true)
        }
    }

    private fun deepSeekNativePrompt(context: Context, request: JSONObject): JSONObject {
        val prompt = request.optString("prompt", "")
        if (prompt.isBlank()) return error("prompt is required")
        if (prompt.length > 12000) return error("prompt too long")

        synchronized(deepSeekResponseLock) {
            if (deepSeekResponseActive) return error("DeepSeek native response already in progress")
            deepSeekResponseActive = true
            deepSeekResponseFinished = false
            deepSeekResponseText = ""
            deepSeekResponseError = null
        }

        var nativeResponse: JSONObject? = null
        var lastError: String? = null
        var bootstrapStarted = false
        val deadline = System.currentTimeMillis() + DEEPSEEK_BOOTSTRAP_WAIT_MS

        while (System.currentTimeMillis() < deadline) {
            try {
                Socket().use { socket ->
                    socket.connect(InetSocketAddress("127.0.0.1", DEEPSEEK_NATIVE_PORT), DEEPSEEK_CONNECT_TIMEOUT_MS)
                    socket.soTimeout = DEEPSEEK_READ_TIMEOUT_MS
                    val writer = PrintWriter(socket.getOutputStream(), true)
                    writer.println(request.toString())
                    val responseLine = BufferedReader(InputStreamReader(socket.getInputStream())).readLine()
                        ?: throw IllegalStateException("DeepSeek native bridge returned no response")
                    nativeResponse = JSONObject(responseLine)
                }
                if (nativeResponse != null) break
            } catch (e: Exception) {
                lastError = e.message ?: e.javaClass.simpleName
                if (!bootstrapStarted) {
                    bootstrapStarted = true
                    val bootstrap = launch(context, "com.deepseek.chat")
                    if (!bootstrap.optBoolean("ok", false)) {
                        clearDeepSeekResponseState()
                        return error("DeepSeek bootstrap failed: " + bootstrap.optString("error", "unknown error"))
                    }
                    Log.i(TAG, "DEEPSEEK_NATIVE_BOOTSTRAP_STARTED")
                }
                Thread.sleep(DEEPSEEK_BOOTSTRAP_POLL_MS)
            }
        }

        val accepted = nativeResponse
        if (accepted == null) {
            clearDeepSeekResponseState()
            return error("DeepSeek native bridge unavailable: " + (lastError ?: "timeout"))
        }
        if (!accepted.optBoolean("accepted", false)) {
            clearDeepSeekResponseState()
            return accepted
        }

        val completed = synchronized(deepSeekResponseLock) {
            val responseDeadline = System.currentTimeMillis() + DEEPSEEK_RESPONSE_TIMEOUT_MS
            while (!deepSeekResponseFinished && deepSeekResponseError == null) {
                val remaining = responseDeadline - System.currentTimeMillis()
                if (remaining <= 0L) break
                deepSeekResponseLock.wait(remaining)
            }
            if (deepSeekResponseFinished) {
                JSONObject().apply {
                    put("ok", true)
                    put("accepted", true)
                    put("completed", true)
                    put("text", deepSeekResponseText)
                }
            } else {
                error(deepSeekResponseError ?: "DeepSeek native response timed out")
            }
        }
        clearDeepSeekResponseState()
        return completed
    }
    private fun clearDeepSeekResponseState() {
        synchronized(deepSeekResponseLock) {
            deepSeekResponseActive = false
            deepSeekResponseFinished = false
            deepSeekResponseText = ""
            deepSeekResponseError = null
            deepSeekResponseLock.notifyAll()
        }
    }

    private fun health(): JSONObject {
        val service = NovaAccessibilityService.instance
        val root = service?.rootInActiveWindow
        val activePackage = root?.packageName?.toString()
        root?.recycle()
        return JSONObject().apply {
            put("ok", true)
            put("bridge", "running")
            put("accessibility_connected", service != null)
            put("active_package", activePackage ?: JSONObject.NULL)
            put("operational", service != null)
        }
    }

    private fun observe(): JSONObject {
        val service = NovaAccessibilityService.instance
        val root = service?.rootInActiveWindow
        if (root != null) {
            ObservationStore.update(root)
            root.recycle()
        }
        val snapshot = ObservationStore.current()
        val elements = JSONArray()
        snapshot.elements.forEach { e ->
            elements.put(JSONObject().apply {
                put("id", e.id)
                put("text", e.text)
                put("contentDescription", e.contentDescription)
                put("clickable", e.clickable)
                put("enabled", e.enabled)
                put("className", e.className)
                put("bounds", e.bounds)
                put("editable", e.editable)
                put("scrollable", e.scrollable)
                put("checkable", e.checkable)
                put("checked", e.checked)
                put("focused", e.focused)
                put("visible", e.visible)
            })
        }
        return JSONObject().apply {
            put("ok", true)
            put("state", JSONObject().apply {
                put("observationId", snapshot.observationId.toString())
                put("package", snapshot.packageName)
                put("activity", snapshot.activity)
                put("timestampMs", System.currentTimeMillis())
                put("elements", elements)
            })
        }
    }

    private fun agentGoal(context: Context, request: JSONObject): JSONObject {
        val goal = request.optString("goal", "").trim()
        if (goal.isBlank()) return error("goal is required")
        val deadlineMs = request.optLong("deadlineMs", 0L)
        if (deadlineMs < 0L) return error("deadlineMs must not be negative")
        val task = TaskStore.startNew(context, goal, deadlineMs)
        val intent = NovaTaskService.intent(context, goal, deadlineMs, taskId = task.id)
        return try {
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
            val waitForResult = request.optBoolean("wait", false)
            if (waitForResult) {
                waitForTerminalTask(context, task.id, request.optLong("waitTimeoutMs", 300000L))
            } else {
                JSONObject().apply {
                    put("ok", true)
                    put("accepted", true)
                    put("status", "running")
                    put("taskId", task.id)
                }
            }
        } catch (e: Throwable) {
            error("unable to start Nova task service: " + (e.message ?: e.javaClass.simpleName))
        }
    }

    private fun agentTrace(context: Context, request: JSONObject): JSONObject {
        val requestedTaskId = request.optString("taskId", "").trim().ifBlank { null }
        val taskId = requestedTaskId ?: TaskStore.get(context)?.id
        if (taskId == null) return error("no task id is available for trace")
        val trace = NovaTrace.snapshot(taskId)
        return JSONObject().apply {
            put("ok", true)
            put("taskId", taskId)
            put("events", trace)
        }
    }

    private fun agentDeepSeekTrace(context: Context, request: JSONObject): JSONObject {
        val requestedTaskId = request.optString("taskId", "").trim().ifBlank { null }
        val taskId = requestedTaskId ?: TaskStore.get(context)?.id
        if (taskId == null) return error("no task id is available for DeepSeek trace")

        val full = request.optBoolean("full", false)
        val events = NovaTrace.snapshot(taskId)
        val messages = JSONArray()
        for (i in 0 until events.length()) {
            val event = events.optJSONObject(i) ?: continue
            if (event.optString("source") != "DEEPSEEK") continue
            when (event.optString("event")) {
                "request" -> messages.put(
                    if (full) {
                        JSONObject().apply {
                            put("type", "request")
                            put("timestampMs", event.optLong("timestampMs"))
                            put("attempt", event.optInt("attempt", 1))
                            put("prompt", event.optString("prompt", ""))
                        }
                    } else {
                        compactDeepSeekRequest(event)
                    }
                )
                "response" -> messages.put(JSONObject().apply {
                    put("type", "response")
                    put("timestampMs", event.optLong("timestampMs"))
                    put("attempt", event.optInt("attempt", 1))
                    put("response", event.optString("response", ""))
                })
                "error" -> messages.put(JSONObject().apply {
                    put("type", "error")
                    put("timestampMs", event.optLong("timestampMs"))
                    put("attempt", event.optInt("attempt", 1))
                    put("error", event.optString("error", "DeepSeek reasoning error"))
                })
            }
        }

        return JSONObject().apply {
            put("ok", true)
            put("taskId", taskId)
            put("full", full)
            put("messages", messages)
        }
    }

    private fun compactDeepSeekRequest(event: JSONObject): JSONObject {
        val prompt = event.optString("prompt", "")
        val mode = when {
            prompt.contains("TURN MODE: GOAL_VERIFICATION") -> "GOAL_VERIFICATION"
            prompt.contains("TURN MODE: ACTION_DECISION") -> "ACTION_DECISION"
            else -> "BOOTSTRAP"
        }

        val result = JSONObject().apply {
            put("type", "request")
            put("timestampMs", event.optLong("timestampMs"))
            put("attempt", event.optInt("attempt", 1))
            put("mode", mode)
        }

        val goal = extractLineValue(prompt, "GOAL:")
        if (!goal.isNullOrBlank()) result.put("goal", goal)

        val observationText = extractPromptJson(prompt, "CURRENT_STATE:")
            ?: extractPromptJson(prompt, "CURRENT_CONTEXT:")
        if (observationText != null) {
            runCatching {
                val envelope = JSONObject(observationText)
                val state = envelope.optJSONObject("current_state") ?: envelope
                val observation = JSONObject().apply {
                    put("observationId", state.optString("observation_id", state.optString("observationId", "")))
                    put("package", state.optString("package", ""))
                    put("activity", state.optString("activity", ""))
                    put("elementCount", state.optJSONArray("elements")?.length() ?: 0)
                }
                result.put("observation", observation)
            }
        }

        return result
    }

    private fun extractLineValue(text: String, marker: String): String? {
        val start = text.indexOf(marker)
        if (start < 0) return null
        val valueStart = start + marker.length
        val lineEnd = text.indexOf('\n', valueStart)
        val value = if (lineEnd >= 0) text.substring(valueStart, lineEnd) else text.substring(valueStart)
        return value.trim().takeIf { it.isNotEmpty() }
    }

    private fun extractPromptJson(text: String, marker: String): String? {
        val markerIndex = text.indexOf(marker)
        if (markerIndex < 0) return null
        val jsonStart = text.indexOf('{', markerIndex + marker.length)
        if (jsonStart < 0) return null

        var depth = 0
        var inString = false
        var escaped = false
        for (i in jsonStart until text.length) {
            val ch = text[i]
            if (inString) {
                if (escaped) {
                    escaped = false
                } else if (ch == '\\') {
                    escaped = true
                } else if (ch == '"') {
                    inString = false
                }
                continue
            }
            when (ch) {
                '"' -> inString = true
                '{' -> depth++
                '}' -> {
                    depth--
                    if (depth == 0) return text.substring(jsonStart, i + 1)
                }
            }
        }
        return null
    }

    private fun agentResult(context: Context, request: JSONObject): JSONObject {
        val requestedTaskId = request.optString("taskId", "").trim().ifBlank { null }
        val current = TaskStore.get(context)
        val taskId = requestedTaskId ?: current?.id
        if (taskId == null) {
            return error("no active or completed task is available")
        }
        return waitForTerminalTask(context, taskId, request.optLong("waitTimeoutMs", 300000L))
    }

    private fun waitForTerminalTask(
        context: Context,
        taskId: String,
        timeoutMs: Long,
    ): JSONObject {
        val timeout = timeoutMs.coerceIn(1000L, 600000L)
        val deadline = System.currentTimeMillis() + timeout
        while (System.currentTimeMillis() < deadline) {
            val task = TaskStore.get(context)
            if (task != null && task.id == taskId && task.status !in setOf("running", "pending")) {
                return JSONObject().apply {
                    put("ok", task.status == "succeeded")
                    put("completed", true)
                    put("task", TaskStore.snapshotJson(context))
                }
            }
            Thread.sleep(250L)
        }
        return JSONObject().apply {
            put("ok", true)
            put("completed", false)
            put("timeout", true)
            put("task", TaskStore.snapshotJson(context))
        }
    }

    private fun agentStatus(context: Context): JSONObject {
        val task = TaskStore.get(context)
        return JSONObject().apply {
            put("ok", true)
            put("task", if (task == null) JSONObject.NULL else TaskStore.snapshotJson(context))
        }
    }

    private fun agentCancel(context: Context): JSONObject {
        val task = TaskStore.cancel(context)
        context.stopService(Intent(context, NovaTaskService::class.java))
        return JSONObject().apply {
            put("ok", true)
            put("accepted", task != null)
            put("task", if (task == null) JSONObject.NULL else TaskStore.snapshotJson(context))
        }
    }
    private fun click(elementId: String): JSONObject {
        val service = NovaAccessibilityService.instance ?: return error("Nova accessibility service is not connected")
        val root = service.rootInActiveWindow ?: return error("No active accessibility window")
        ObservationStore.update(root)
        val before = ObservationStore.current()
        val node = findNode(root, elementId) ?: run {
            root.recycle()
            return error("element not found: $elementId")
        }
        val accepted = node.isEnabled && node.isClickable && node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
        node.recycle()
        root.recycle()
        val changed = accepted && waitForObservableChange(service, before)
        return JSONObject().apply {
            put("ok", true)
            put("accepted", accepted)
            put("changed", changed)
        }
    }

    private fun waitForObservableChange(service: NovaAccessibilityService, before: UiSnapshot): Boolean {
        val deadline = System.currentTimeMillis() + ACTION_CHANGE_TIMEOUT_MS
        while (System.currentTimeMillis() < deadline) {
            val root = service.rootInActiveWindow
            if (root != null) {
                ObservationStore.update(root)
                root.recycle()
                val current = ObservationStore.current()
                if (!sameUi(before, current)) return true
            }
            Thread.sleep(OBSERVATION_POLL_MS)
        }
        return false
    }

    private fun sameUi(before: UiSnapshot, after: UiSnapshot): Boolean =
        before.packageName == after.packageName &&
            before.activity == after.activity &&
            before.elements == after.elements

    private fun findNode(root: AccessibilityNodeInfo, id: String): AccessibilityNodeInfo? = findNode(root, id, "0")

    private fun findNode(node: AccessibilityNodeInfo, id: String, path: String): AccessibilityNodeInfo? {
        if (node.viewIdResourceName == id || "path:$path" == id) return node
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val result = findNode(child, id, "$path.$i")
            if (result != null) {
                if (result !== child) child.recycle()
                return result
            }
            child.recycle()
        }
        return null
    }

    private fun scroll(elementId: String): JSONObject {
        val service = NovaAccessibilityService.instance ?: return error("Nova accessibility service is not connected")
        val root = service.rootInActiveWindow ?: return error("No active accessibility window")
        ObservationStore.update(root)
        val before = ObservationStore.current()
        val node = findNode(root, elementId) ?: run {
            root.recycle()
            return error("element not found: $elementId")
        }
        val accepted = if (!node.isEnabled || !node.isScrollable) {
            false
        } else {
            node.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD) ||
                if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.M) {
                    node.performAction(AccessibilityNodeInfo.ACTION_SCROLL_DOWN)
                } else {
                    false
                }
        }
        node.recycle()
        root.recycle()
        val changed = accepted && waitForObservableChange(service, before)
        return JSONObject().apply {
            put("ok", true)
            put("accepted", accepted)
            put("changed", changed)
        }
    }

    private fun back(): JSONObject {
        val service = NovaAccessibilityService.instance ?: return error("Nova accessibility service is not connected")
        val accepted = service.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
        return JSONObject().apply {
            put("ok", true)
            put("accepted", accepted)
            put("changed", accepted)
        }
    }

    private fun launch(context: Context, packageName: String): JSONObject {
        val intent = if (packageName == "com.deepseek.chat") {
            Intent().setClassName(packageName, "com.deepseek.chat.MainActivity").apply {
                putExtra("com.hausshehe.nova.HEADLESS_BOOTSTRAP", true)
            }
        } else {
            context.packageManager.getLaunchIntentForPackage(packageName)
        } ?: return error("launch intent not found: $packageName")
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)

        if (packageName == "com.deepseek.chat") {
            try {
                val optionsClass = Class.forName("android.app.ActivityOptions")
                val options = optionsClass.getMethod("makeBasic").invoke(null)
                optionsClass.getMethod("setAvoidMoveToFront").invoke(options)
                val bundle = optionsClass.getMethod("toBundle").invoke(options) as android.os.Bundle
                context.startActivity(intent, bundle)
                Log.i(TAG, "DeepSeek launched with avoidMoveToFront")
            } catch (e: Throwable) {
                Log.w(TAG, "DeepSeek invisible launch option unavailable; using normal launch: ${e.message}")
                context.startActivity(intent)
            }
        } else {
            context.startActivity(intent)
        }

        if (packageName == "com.deepseek.chat") {
            return JSONObject().apply {
                put("ok", true)
                put("accepted", true)
                put("backgroundBootstrap", true)
            }
        }

        val service = NovaAccessibilityService.instance ?: return error("Nova accessibility service is not connected")
        val deadline = System.currentTimeMillis() + LAUNCH_WAIT_MS
        while (System.currentTimeMillis() < deadline) {
            val root = service.rootInActiveWindow
            val activePackage = root?.packageName?.toString()
            if (activePackage == packageName) {
                if (root != null) {
                    ObservationStore.update(root)
                    root.recycle()
                }
                return JSONObject().apply { put("ok", true); put("accepted", true) }
            }
            root?.recycle()
            Thread.sleep(OBSERVATION_POLL_MS)
        }
        val activePackage = service.rootInActiveWindow?.packageName?.toString()
        return error("launch timed out waiting for accessibility window: expected=$packageName active=$activePackage")
    }

    private fun openUri(context: Context, uriValue: String, packageName: String?): JSONObject {
        if (uriValue.isBlank()) return error("uri is required")
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(uriValue)).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            if (!packageName.isNullOrBlank()) setPackage(packageName)
        }
        return try {
            context.startActivity(intent)
            JSONObject().apply { put("ok", true); put("accepted", true) }
        } catch (e: Exception) {
            error("unable to open URI: ${e.message ?: "unknown error"}")
        }
    }

    private fun shareText(context: Context, text: String, packageName: String, component: String): JSONObject {
        if (text.isBlank()) return error("text is required")
        if (packageName.isBlank()) return error("package is required")
        if (component.isBlank()) return error("component is required")
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, text)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            setClassName(packageName, component)
        }
        return try {
            context.startActivity(intent)
            JSONObject().apply { put("ok", true); put("accepted", true) }
        } catch (e: Exception) {
            error("unable to share text: ${e.message ?: "unknown error"}")
        }
    }

    private fun error(message: String): JSONObject = JSONObject().apply {
        put("ok", false)
        put("error", message)
    }
}
