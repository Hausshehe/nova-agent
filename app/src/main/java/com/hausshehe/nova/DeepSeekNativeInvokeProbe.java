package com.hausshehe.nova;

import android.util.Log;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.ArrayList;
import java.util.List;

import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

/**
 * Controlled native completion bridge for DeepSeek.
 *
 * A real DeepSeek send is used only to capture the live session context. The
 * actual native completion is invoked only after Nova sends a command over the
 * loopback control socket. No prompt content is logged.
 */
public final class DeepSeekNativeInvokeProbe implements IXposedHookLoadPackage {
    private static final String TAG = "NovaDeepSeekHook";
    private static final String TARGET_PACKAGE = "com.deepseek.chat";
    private static final int CONTROL_PORT = 18766;
    private static final int MAX_PROMPT_LENGTH = 12000;

    private static volatile Object liveNp1;
    private static volatile Object liveXr;
    private static volatile Object liveSv8;
    private static volatile boolean liveThinking;
    private static volatile boolean liveSearch;

    @Override
    public void handleLoadPackage(XC_LoadPackage.LoadPackageParam lpparam) {
        if (!TARGET_PACKAGE.equals(lpparam.packageName)) return;
        try {
            hookRealB18Send(lpparam.classLoader);
            startControlServer(lpparam.classLoader);
            Log.i(TAG, "DEEPSEEK_NATIVE_INVOKE_BRIDGE_INSTALLED port=" + CONTROL_PORT);
        } catch (Throwable t) {
            Log.e(TAG, "DEEPSEEK_NATIVE_INVOKE_BRIDGE_FAILED", t);
        }
    }

    private static void hookRealB18Send(ClassLoader cl) {
        Class<?> b18 = XposedHelpers.findClass("b18", cl);
        Class<?> xr = XposedHelpers.findClass("xr", cl);
        Class<?> sv8 = XposedHelpers.findClass("sv8", cl);
        Class<?> ew1 = XposedHelpers.findClass("ew1", cl);
        Class<?> yg2 = XposedHelpers.findClass("yg2", cl);

        XposedHelpers.findAndHookMethod(
                b18, "v", xr, String.class, Integer.class, List.class,
                boolean.class, boolean.class, String.class, sv8, ew1, yg2,
                new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) {
                        Object prompt = param.args[1];
                        Object context = param.args[9];
                        if (!(prompt instanceof String) || ((String) prompt).length() == 0
                                || context == null || !"ap1".equals(context.getClass().getSimpleName())) {
                            return;
                        }

                        try {
                            Object np1 = XposedHelpers.getObjectField(context, "i");
                            liveNp1 = np1;
                            liveXr = param.args[0];
                            liveSv8 = param.args[7];
                            liveThinking = ((Boolean) param.args[4]).booleanValue();
                            liveSearch = ((Boolean) param.args[5]).booleanValue();
                            Log.i(TAG, "DEEPSEEK_NATIVE_CONTEXT_CAPTURED np1=" + identity(np1)
                                    + " thinking=" + liveThinking + " search=" + liveSearch);
                        } catch (Throwable t) {
                            liveNp1 = null;
                            liveXr = null;
                            liveSv8 = null;
                            Log.e(TAG, "DEEPSEEK_NATIVE_CONTEXT_CAPTURE_FAILED", t);
                        }
                    }
                });
    }

    private static void startControlServer(final ClassLoader cl) {
        Thread serverThread = new Thread(() -> {
            try (ServerSocket server = new ServerSocket(
                    CONTROL_PORT, 16, InetAddress.getByName("127.0.0.1"))) {
                while (true) {
                    final Socket socket = server.accept();
                    Thread client = new Thread(() -> handleControl(socket), "NovaDeepSeekNativeClient");
                    client.setDaemon(true);
                    client.start();
                }
            } catch (Throwable t) {
                Log.e(TAG, "DEEPSEEK_NATIVE_CONTROL_SERVER_FAILED", t);
            }
        }, "NovaDeepSeekNativeControl");
        serverThread.setDaemon(true);
        serverThread.start();
    }

    private static void handleControl(Socket socket) {
        try (Socket s = socket) {
            BufferedReader reader = new BufferedReader(new InputStreamReader(s.getInputStream()));
            PrintWriter writer = new PrintWriter(s.getOutputStream(), true);
            String line = reader.readLine();
            if (line == null || line.length() == 0) {
                writer.println(error("empty request").toString());
                return;
            }

            JSONObject request = new JSONObject(line);
            if (!"deepseek_native_prompt".equals(request.optString("command"))) {
                writer.println(error("unknown command").toString());
                return;
            }

            String prompt = request.optString("prompt", "");
            if (prompt.length() == 0) {
                writer.println(error("prompt is required").toString());
                return;
            }
            if (prompt.length() > MAX_PROMPT_LENGTH) {
                writer.println(error("prompt too long").toString());
                return;
            }

            Object np1 = liveNp1;
            Object xr = liveXr;
            Object sv8 = liveSv8;
            if (np1 == null || xr == null) {
                writer.println(error("DeepSeek native session context is not ready; send one normal DeepSeek message first").toString());
                return;
            }

            try {
                XposedHelpers.callStaticMethod(
                        np1.getClass(),
                        "V",
                        np1,
                        prompt,
                        new ArrayList<>(),
                        null,
                        sv8,
                        xr,
                        liveThinking,
                        liveSearch,
                        false);

                Log.i(TAG, "DEEPSEEK_NATIVE_INVOKE_STARTED np1=" + identity(np1)
                        + " promptLength=" + prompt.length());
                writer.println(ok().toString());
            } catch (Throwable t) {
                Log.e(TAG, "DEEPSEEK_NATIVE_INVOKE_FAILED", t);
                writer.println(error("native invocation failed: " + t.getClass().getSimpleName()).toString());
            }
        } catch (Throwable t) {
            Log.e(TAG, "DEEPSEEK_NATIVE_CONTROL_REQUEST_FAILED", t);
        }
    }

    private static JSONObject ok() {
        JSONObject result = new JSONObject();
        try {
            result.put("ok", true);
            result.put("accepted", true);
        } catch (Throwable ignored) {
        }
        return result;
    }

    private static JSONObject error(String message) {
        JSONObject result = new JSONObject();
        try {
            result.put("ok", false);
            result.put("error", message);
        } catch (Throwable ignored) {
        }
        return result;
    }

    private static String identity(Object value) {
        return value == null ? "null" : value.getClass().getSimpleName() + "@" + System.identityHashCode(value);
    }
}
