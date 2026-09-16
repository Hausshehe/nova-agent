package com.hausshehe.nova;

import android.util.Log;

import java.util.ArrayList;
import java.util.List;

import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

/**
 * Focused one-shot probe for DeepSeek's high-level native completion launcher.
 *
 * The first real user send captures the live session np1 from ap1. A guarded
 * invocation then calls DeepSeek's own static np1.V(...) launcher with a fixed
 * probe prompt. It deliberately does not call the lower b18.v boundary itself.
 */
public final class DeepSeekNativeInvokeProbe implements IXposedHookLoadPackage {
    private static final String TAG = "NovaDeepSeekHook";
    private static final String TARGET_PACKAGE = "com.deepseek.chat";
    private static final String PROBE_PROMPT = "Nova native invocation probe. Reply with exactly: NATIVE_OK";

    private static volatile Object liveNp1;
    private static volatile boolean invocationStarted;

    @Override
    public void handleLoadPackage(XC_LoadPackage.LoadPackageParam lpparam) {
        if (!TARGET_PACKAGE.equals(lpparam.packageName)) return;
        try {
            hookRealB18Send(lpparam.classLoader);
            Log.i(TAG, "DEEPSEEK_NATIVE_INVOKE_PROBE_INSTALLED");
        } catch (Throwable t) {
            Log.e(TAG, "DEEPSEEK_NATIVE_INVOKE_PROBE_FAILED", t);
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
                            liveNp1 = XposedHelpers.getObjectField(context, "i");
                        } catch (Throwable t) {
                            liveNp1 = null;
                            Log.e(TAG, "DEEPSEEK_NATIVE_NP1_CAPTURE_FAILED", t);
                            return;
                        }

                        Log.i(TAG, "DEEPSEEK_NATIVE_CONTEXT_CAPTURED np1=" + identity(liveNp1));

                        if (invocationStarted || liveNp1 == null) return;
                        invocationStarted = true;

                        try {
                            Class<?> np1Class = liveNp1.getClass();
                            Object sv8Value = param.args[7];
                            Object xrValue = param.args[0];
                            boolean thinking = ((Boolean) param.args[4]).booleanValue();
                            boolean search = ((Boolean) param.args[5]).booleanValue();

                            XposedHelpers.callStaticMethod(
                                    np1Class,
                                    "V",
                                    liveNp1,
                                    PROBE_PROMPT,
                                    new ArrayList<>(),
                                    null,
                                    sv8Value,
                                    xrValue,
                                    thinking,
                                    search,
                                    false);

                            Log.i(TAG, "DEEPSEEK_NATIVE_INVOKE_STARTED np1=" + identity(liveNp1)
                                    + " promptLength=" + PROBE_PROMPT.length());
                        } catch (Throwable t) {
                            Log.e(TAG, "DEEPSEEK_NATIVE_INVOKE_FAILED", t);
                        }
                    }
                });
    }

    private static String identity(Object value) {
        return value == null ? "null" : value.getClass().getSimpleName() + "@" + System.identityHashCode(value);
    }
}
