package com.hausshehe.nova

import android.content.Context
import android.content.Intent
import android.util.Log
import android.view.accessibility.AccessibilityNodeInfo
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.PrintWriter
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.Executors

object BridgeServer {
    private const val TAG = "NovaBridgeServer"
    private const val PORT = 18765
    private const val PACKAGE = "com.hausshehe.nova"
    private const val START_RETRIES = 20
    private const val RETRY_DELAY_MS = 250L
    private const val LAUNCH_WAIT_MS = 3000L
    private const val OBSERVATION_POLL_MS = 100L
    private val executor = Executors.newCachedThreadPool()
    @Volatile private var started = false

    @Synchronized
    fun start(context: Context) {
        if (started) {
            Log.d(TAG, "start(): already started")
            return
        }

        started = true
        Log.i(TAG, "start(): starting localhost bridge on 127.0.0.1:$PORT")
        executor.execute { serve(context.applicationContext) }
    }

    private fun serve(context: Context) {
        var server: ServerSocket? = null

        try {
            for (attempt in 1..START_RETRIES) {
                try {
                    server = ServerSocket(PORT, 50, InetAddress.getByName("127.0.0.1"))
                    Log.i(TAG, "Bridge listening on 127.0.0.1:$PORT")
                    break
                } catch (e: Exception) {
                    Log.e(
                        TAG,
                        "Bridge bind failed (attempt $attempt/$START_RETRIES): ${e.javaClass.simpleName}: ${e.message}",
                        e
                    )
                    if (attempt < START_RETRIES) {
                        try {
                            Thread.sleep(RETRY_DELAY_MS)
                        } catch (interrupted: InterruptedException) {
                            Thread.currentThread().interrupt()
                            return
                        }
                    }
                }
            }

            val listeningServer = server
            if (listeningServer == null) {
                Log.e(TAG, "Bridge failed to bind 127.0.0.1:$PORT after $START_RETRIES attempts")
                return
            }

            listeningServer.use { boundServer ->
                while (true) {
                    val socket = boundServer.accept()
                    Log.d(TAG, "Accepted bridge connection from ${socket.remoteSocketAddress}")
                    executor.execute { handle(context, socket) }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Bridge server stopped unexpectedly: ${e.javaClass.simpleName}: ${e.message}", e)
        } finally {
            server?.takeIf { !it.isClosed }?.close()
            started = false
            Log.w(TAG, "Bridge server stopped; started=false")
        }
    }

    private fun handle(context: Context, socket: Socket) {
        socket.use { s ->
            try {
                val reader = BufferedReader(InputStreamReader(s.getInputStream()))
                val writer = PrintWriter(s.getOutputStream(), true)
                val line = reader.readLine() ?: return
                val request = JSONObject(line)
                Log.d(TAG, "Request: ${request.optString("command")}")
                val response = when (request.optString("command")) {
                    "observe" -> observe()
                    "click" -> click(request.optString("elementId"))
                    "back" -> back()
                    "launch" -> launch(context, request.optString("package", PACKAGE))
                    else -> error("unknown command: ${request.optString("command")}")
                }
                writer.println(response.toString())
            } catch (e: Exception) {
                Log.e(TAG, "Bridge request failed: ${e.javaClass.simpleName}: ${e.message}", e)
                PrintWriter(s.getOutputStream(), true).println(error(e.message ?: "bridge error").toString())
            }
        }
    }

    private fun observe(): JSONObject {
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
                put("package", PACKAGE)
                put("activity", "$PACKAGE.MainActivity")
                put("timestampMs", System.currentTimeMillis())
                put("elements", elements)
            })
        }
    }

    private fun click(elementId: String): JSONObject {
        val service = NovaAccessibilityService.instance
            ?: return error("Nova accessibility service is not connected")
        val root = service.rootInActiveWindow
            ?: return error("No active accessibility window")
        val node = findNode(root, elementId)
            ?: return error("element not found: $elementId")

        val accepted = node.isEnabled && node.isClickable &&
            node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
        node.recycle()

        return JSONObject().apply {
            put("ok", true)
            put("accepted", accepted)
            put("changed", accepted)
        }
    }

    private fun findNode(root: AccessibilityNodeInfo, id: String): AccessibilityNodeInfo? =
        findNode(root, id, "0")

    private fun findNode(
        node: AccessibilityNodeInfo,
        id: String,
        path: String
    ): AccessibilityNodeInfo? {
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
        val service = NovaAccessibilityService.instance
            ?: return error("Nova accessibility service is not connected")
        val accepted = service.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK)
        return JSONObject().apply {
            put("ok", true)
            put("accepted", accepted)
            put("changed", accepted)
        }
    }

    private fun launch(context: Context, packageName: String): JSONObject {
        val intent = context.packageManager.getLaunchIntentForPackage(packageName)
            ?: return error("launch intent not found: $packageName")
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        context.startActivity(intent)

        val service = NovaAccessibilityService.instance
        if (service == null) {
            return error("Nova accessibility service is not connected")
        }

        val deadline = System.currentTimeMillis() + LAUNCH_WAIT_MS
        while (System.currentTimeMillis() < deadline) {
            val root = service.rootInActiveWindow
            val activePackage = root?.packageName?.toString()
            if (activePackage == packageName) {
                ObservationStore.update(root)
                Log.i(TAG, "Launch synchronized with accessibility window: $activePackage")
                return JSONObject().apply {
                    put("ok", true)
                    put("accepted", true)
                }
            }
            root?.recycle()
            try {
                Thread.sleep(OBSERVATION_POLL_MS)
            } catch (interrupted: InterruptedException) {
                Thread.currentThread().interrupt()
                return error("launch wait interrupted")
            }
        }

        val activePackage = service.rootInActiveWindow?.packageName?.toString()
        Log.e(TAG, "Launch did not reach target package $packageName; active package=$activePackage")
        return error("launch timed out waiting for accessibility window: expected=$packageName active=$activePackage")
    }

    private fun error(message: String): JSONObject = JSONObject().apply {
        put("ok", false)
        put("error", message)
    }
}
