package com.hausshehe.nova

import android.content.Context
import android.content.Intent
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
    private const val PORT = 18765
    private const val PACKAGE = "com.hausshehe.nova"
    private val executor = Executors.newCachedThreadPool()
    @Volatile private var started = false

    @Synchronized
    fun start(context: Context) {
        if (started) return
        started = true
        executor.execute { serve(context.applicationContext) }
    }

    private fun serve(context: Context) {
        try {
            ServerSocket(PORT, 50, InetAddress.getByName("127.0.0.1")).use { server ->
                while (true) {
                    val socket = server.accept()
                    executor.execute { handle(context, socket) }
                }
            }
        } catch (_: Exception) {
            started = false
        }
    }

    private fun handle(context: Context, socket: Socket) {
        socket.use { s ->
            try {
                val reader = BufferedReader(InputStreamReader(s.getInputStream()))
                val writer = PrintWriter(s.getOutputStream(), true)
                val line = reader.readLine() ?: return
                val request = JSONObject(line)
                val response = when (request.optString("command")) {
                    "observe" -> observe()
                    "click" -> click(request.optString("elementId"))
                    "back" -> back()
                    "launch" -> launch(context, request.optString("package", PACKAGE))
                    else -> error("unknown command: ${request.optString("command")}")
                }
                writer.println(response.toString())
            } catch (e: Exception) {
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

    private fun findNode(root: AccessibilityNodeInfo, id: String): AccessibilityNodeInfo? {
        if (root.viewIdResourceName == id) return root
        for (i in 0 until root.childCount) {
            val child = root.getChild(i) ?: continue
            val result = findNode(child, id)
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
        return JSONObject().apply {
            put("ok", true)
            put("accepted", true)
        }
    }

    private fun error(message: String): JSONObject = JSONObject().apply {
        put("ok", false)
        put("error", message)
    }
}
