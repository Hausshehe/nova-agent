package com.hausshehe.nova;

import android.util.Log;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;

import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

/**
 * Controlled native completion bridge for DeepSeek.
 *
 * Nova enters DeepSeek's own higher-level session/send path instead of calling
 * the lower-level V() method with a previously warmed xr. DeepSeek therefore
 * retains ownership of session-state checks, bootstrap/recovery decisions, and
 * the native completion machinery.
 */
public final class DeepSeekNativeInvokeProbe implements IXposedHookLoadPackage {
    private static final String TAG = "NovaDeepSeekHook";
    private static final String TARGET_PACKAGE = "com.deepseek.chat";
    private static final int CONTROL_PORT = 18766;
    private static final int MAX_PROMPT_LENGTH = 12000;
    private static final int U_DEFAULT_MASK = 0x4c;

    public DeepSeekNativeInvokeProbe() {
    }

    private static volatile Object liveNp1;

    @Override
    public void handleLoadPackage(XC_LoadPackage.LoadPackageParam lpparam) {
        Log.i(TAG, "DEEPSEEK_NATIVE_LPPARAM_RECEIVED package=" + lpparam.packageName
                + " process=" + lpparam.processName);
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
                b18, "v", xr, String.class, Integer.class, java.util.List.class,
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
                            liveNp1 = XposedHelpers.getObjectField(context, "i");
                            Log.i(TAG, "DEEPSEEK_NATIVE_CONTEXT_CAPTURED np1=" + identity(liveNp1)
                                    + " thinking=" + param.args[4] + " search=" + param.args[5]);
                        } catch (Throwable t) {
                            liveNp1 = null;
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
        Log.i(TAG, "DEEPSEEK_NATIVE_CONTROL_HANDLER_ENTERED");
        try (Socket s = socket) {
            BufferedReader reader = new BufferedReader(new InputStreamReader(s.getInputStream()));
            PrintWriter writer = new PrintWriter(s.getOutputStream(), true);
            String line = reader.readLine();
            Log.i(TAG, "DEEPSEEK_NATIVE_CONTROL_REQUEST_RECEIVED hasLine=" + (line != null));
            if (line == null || line.length() == 0) {
                writer.println(error("empty request").toString());
                return;
            }

            JSONObject request = new JSONObject(line);
            Log.i(TAG, "DEEPSEEK_NATIVE_CONTROL_COMMAND_PARSED command="
                    + request.optString("command"));
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
            if (np1 == null) {
                writer.println(error("DeepSeek native session object is not ready").toString());
                return;
            }

            try {
                Object refs = XposedHelpers.callMethod(
                        XposedHelpers.callMethod(
                                XposedHelpers.callMethod(np1, "Q"), "l"), "a");
                Object nativeN1 = XposedHelpers.callMethod(refs, "k");

                long startedAt = System.nanoTime();
                Log.i(TAG, "DEEPSEEK_NATIVE_U_CALLING np1=" + identity(np1)
                        + " n1=" + identity(nativeN1)
                        + " promptLength=" + prompt.length()
                        + " mask=" + U_DEFAULT_MASK);

                XposedHelpers.callStaticMethod(
                        np1.getClass(),
                        "U",
                        np1,
                        prompt,
                        nativeN1,
                        null,
                        false,
                        U_DEFAULT_MASK);

                long elapsedMs = (System.nanoTime() - startedAt) / 1_000_000L;
                Log.i(TAG, "DEEPSEEK_NATIVE_U_RETURNED np1=" + identity(np1)
                        + " elapsedMs=" + elapsedMs);
                writer.println(ok().toString());
            } catch (Throwable t) {
                Log.e(TAG, "DEEPSEEK_NATIVE_U_FAILED", t);
                writer.println(error("native U invocation failed: " + t.getClass().getSimpleName()).toString());
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
