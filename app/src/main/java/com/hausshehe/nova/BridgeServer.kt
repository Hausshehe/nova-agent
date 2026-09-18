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
                val request = JSONObject(reader.readLine() ?: return)
                val response = when (request.optString("command")) {
                    "observe" -> observe()
                    "health" -> health()
                    "deepseek_event" -> deepSeekEvent(request)
                    "deepseek_native_prompt" -> deepSeekNativePrompt(request)
                    "click" -> click(request.optString("elementId"))
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

    private fun deepSeekNativePrompt(request: JSONObject): JSONObject {
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

        val accepted = try {
            Socket().use { socket ->
                socket.connect(
                    InetSocketAddress("127.0.0.1", DEEPSEEK_NATIVE_PORT),
                    DEEPSEEK_CONNECT_TIMEOUT_MS,
                )
                socket.soTimeout = DEEPSEEK_READ_TIMEOUT_MS
                val writer = PrintWriter(socket.getOutputStream(), true)
                writer.println(request.toString())
                val responseLine = BufferedReader(InputStreamReader(socket.getInputStream())).readLine()
                    ?: return error("DeepSeek native bridge returned no response").also { clearDeepSeekResponseState() }
                val nativeResponse = JSONObject(responseLine)
                if (!nativeResponse.optBoolean("accepted", false)) {
                    clearDeepSeekResponseState()
                }
                nativeResponse
            }
        } catch (e: Exception) {
            clearDeepSeekResponseState()
            return error("DeepSeek native bridge unavailable: ${e.message ?: e.javaClass.simpleName}")
        }

        if (!accepted.optBoolean("accepted", false)) return accepted

        val completed = synchronized(deepSeekResponseLock) {
            val deadline = System.currentTimeMillis() + DEEPSEEK_RESPONSE_TIMEOUT_MS
            while (!deepSeekResponseFinished && deepSeekResponseError == null) {
                val remaining = deadline - System.currentTimeMillis()
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
        val activePackage = service?.rootInActiveWindow?.packageName?.toString()
        return JSONObject().apply {
            put("ok", true)
            put("bridge", "running")
            put("accessibility_connected", service != null)
            put("active_package", activePackage ?: JSONObject.NULL)
            put("operational", service != null && activePackage == PACKAGE)
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
        val intent = context.packageManager.getLaunchIntentForPackage(packageName) ?: return error("launch intent not found: $packageName")
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
