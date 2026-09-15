package com.hausshehe.nova;

import android.util.Log;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Fire-and-forget transport from the injected DeepSeek process to Nova's
 * localhost bridge. The DeepSeek hook never depends on the bridge being up.
 */
public final class DeepSeekBridgeClient {
    private static final String TAG = "NovaDeepSeekBridge";
    private static final String HOST = "127.0.0.1";
    private static final int PORT = 18765;
    private static final int CONNECT_TIMEOUT_MS = 250;
    private static final int READ_TIMEOUT_MS = 250;

    private static final ExecutorService EXECUTOR = Executors.newSingleThreadExecutor(r -> {
        Thread thread = new Thread(r, "NovaDeepSeekBridge");
        thread.setDaemon(true);
        return thread;
    });

    private DeepSeekBridgeClient() {
    }

    public static void sendStarted(String type, int id) {
        send(event("started", type, id));
    }

    public static void sendDelta(String type, int id, String delta) {
        send(event("delta", type, id).put("delta", safe(delta)));
    }

    public static void sendReplaced(String type, int id, String text) {
        send(event("replaced", type, id).put("text", safe(text)));
    }

    public static void sendFinished(String type, int id, String text) {
        send(event("finished", type, id).put("text", safe(text)));
    }

    private static JSONObject event(String event, String type, int id) {
        return new JSONObject()
                .put("command", "deepseek_event")
                .put("event", event)
                .put("type", safe(type))
                .put("id", id);
    }

    private static void send(final JSONObject request) {
        EXECUTOR.execute(() -> {
            try (Socket socket = new Socket()) {
                socket.connect(new InetSocketAddress(HOST, PORT), CONNECT_TIMEOUT_MS);
                socket.setSoTimeout(READ_TIMEOUT_MS);

                PrintWriter writer = new PrintWriter(socket.getOutputStream(), true);
                writer.println(request.toString());

                BufferedReader reader = new BufferedReader(
                        new InputStreamReader(socket.getInputStream()));
                reader.readLine();
            } catch (Throwable ignored) {
                Log.d(TAG, "DeepSeek bridge unavailable");
            }
        });
    }

    private static String safe(String value) {
        return value == null ? "" : value;
    }
}
