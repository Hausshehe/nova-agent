package com.hausshehe.nova

import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.PrintWriter
import java.net.InetSocketAddress
import java.net.Socket

/**
 * Nova -> DeepSeek reasoning transport.
 *
 * Nova talks only to its local BridgeServer. The bridge owns DeepSeek
 * bootstrap and invokes DeepSeek's in-process native completion machinery.
 */
class NativeReasoningClient(
    private val host: String = "127.0.0.1",
    private val port: Int = 18765,
    private val timeoutMs: Int = 40000,
) : ReasoningProvider {
    fun complete(prompt: String): String {
        require(prompt.isNotBlank()) { "reasoning prompt must not be blank" }

        val request = JSONObject().apply {
            put("command", "deepseek_native_prompt")
            put("prompt", prompt)
        }

        Socket().use { socket ->
            socket.connect(InetSocketAddress(host, port), 2000)
            socket.soTimeout = timeoutMs

            PrintWriter(socket.getOutputStream(), true).println(request.toString())

            val line = BufferedReader(InputStreamReader(socket.getInputStream())).readLine()
                ?: throw IllegalStateException("Nova bridge returned no reasoning response")
            val response = JSONObject(line)

            if (!response.optBoolean("ok", false)) {
                throw IllegalStateException(
                    response.optString("error", "DeepSeek reasoning failed")
                )
            }
            if (!response.optBoolean("completed", false)) {
                throw IllegalStateException("DeepSeek reasoning response was not completed")
            }

            return response.optString("text", "")
                .takeIf { it.isNotBlank() }
                ?: throw IllegalStateException("DeepSeek returned an empty reasoning response")
        }
    }
}
