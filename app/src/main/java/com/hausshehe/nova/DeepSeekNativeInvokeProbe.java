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
            hookSessionResolution(lpparam.classLoader);
            startControlServer(lpparam.classLoader);
            Log.i(TAG, "DEEPSEEK_NATIVE_INVOKE_BRIDGE_INSTALLED port=" + CONTROL_PORT);
        } catch (Throwable t) {
            Log.e(TAG, "DEEPSEEK_NATIVE_INVOKE_BRIDGE_FAILED", t);
        }
    }

    private static void hookSessionResolution(ClassLoader cl) throws ClassNotFoundException {
        Class<?> x05 = XposedHelpers.findClass("x05", cl);
        Class<?> p35 = XposedHelpers.findClass("p35", cl);
        Class<?> f5a = XposedHelpers.findClass("f5a", cl);
        Class<?> pj2 = XposedHelpers.findClass("pj2", cl);
        Class<?> g48 = XposedHelpers.findClass("g48", cl);
        Class<?> kx3 = XposedHelpers.findClass("kx3", cl);

        XposedHelpers.findAndHookMethod(
                x05, "K0", p35, f5a, String.class, pj2, g48, kx3,
                new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) {
                        try {
                            Object kk1 = param.getResult();
                            if (kk1 == null || !"kk1".equals(kk1.getClass().getName())) return;

                            Object d = XposedHelpers.getObjectField(kk1, "d");
                            Object zj1 = d == null ? null : XposedHelpers.callMethod(d, "getValue");
                            Object np1 = zj1 == null ? null : XposedHelpers.getObjectField(zj1, "c");
                            if (np1 != null && "np1".equals(np1.getClass().getName())) {
                                liveNp1 = np1;
                                Log.i(TAG, "DEEPSEEK_NATIVE_SESSION_RESOLVED np1=" + identity(np1)
                                        + " kk1=" + identity(kk1));
                            }
                        } catch (Throwable t) {
                            Log.e(TAG, "DEEPSEEK_NATIVE_SESSION_RESOLVE_FAILED", t);
                        }
                    }
                });
        Log.i(TAG, "DEEPSEEK_NATIVE_SESSION_HOOK_INSTALLED class=x05 method=K0");
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
                Object be1 = XposedHelpers.callMethod(np1, "Q");
                Object lr1 = XposedHelpers.callMethod(be1, "l");
                Object it8 = XposedHelpers.getObjectField(lr1, "a");
                Object nativeN1 = XposedHelpers.callMethod(it8, "k");

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
