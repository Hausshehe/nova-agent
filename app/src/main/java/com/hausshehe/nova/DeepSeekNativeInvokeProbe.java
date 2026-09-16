package com.hausshehe.nova;

import android.util.Log;

import java.util.List;

import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

/**
 * Focused probe for the already-proven native DeepSeek send boundary.
 *
 * This class deliberately does not invoke b18.v automatically. It captures
 * only the runtime context objects observed on a real user send so the next
 * experiment can test a controlled native invocation without rebuilding the
 * entire request path.
 */
public final class DeepSeekNativeInvokeProbe implements IXposedHookLoadPackage {
    private static final String TAG = "NovaDeepSeekHook";
    private static final String TARGET_PACKAGE = "com.deepseek.chat";

    private static volatile Object liveKk1;
    private static volatile Object liveXr;
    private static volatile Object liveB18;

    private static volatile Object lastSv8;
    private static volatile Object lastEw1;
    private static volatile Object lastYg2;
    private static volatile Object lastParentId;
    private static volatile Object lastRefs;

    @Override
    public void handleLoadPackage(XC_LoadPackage.LoadPackageParam lpparam) {
        if (!TARGET_PACKAGE.equals(lpparam.packageName)) return;
        try {
            hookKk1Resolution(lpparam.classLoader);
            hookRealB18Send(lpparam.classLoader);
            Log.i(TAG, "DEEPSEEK_NATIVE_INVOKE_PROBE_INSTALLED");
        } catch (Throwable t) {
            Log.e(TAG, "DEEPSEEK_NATIVE_INVOKE_PROBE_FAILED", t);
        }
    }

    private static void hookKk1Resolution(ClassLoader cl) {
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
                        Object key = param.args.length > 0 ? param.args[0] : null;
                        Object result = param.getResult();
                        if (key == null || result == null) return;
                        String keyName;
                        try {
                            keyName = String.valueOf(XposedHelpers.callMethod(key, "b"));
                        } catch (Throwable ignored) {
                            return;
                        }
                        if (!keyName.contains("kk1") || !"kk1".equals(result.getClass().getSimpleName())) return;

                        liveKk1 = result;
                        try {
                            liveXr = XposedHelpers.callMethod(result, "m");
                            Object p41 = XposedHelpers.getObjectField(result, "h");
                            liveB18 = p41 == null ? null : XposedHelpers.getObjectField(p41, "b");
                            Log.i(TAG, "DEEPSEEK_NATIVE_CONTEXT_RESOLVED kk1="
                                    + System.identityHashCode(result)
                                    + " xr=" + identity(liveXr)
                                    + " b18=" + identity(liveB18));
                        } catch (Throwable t) {
                            Log.e(TAG, "DEEPSEEK_NATIVE_CONTEXT_RESOLVE_FAILED", t);
                        }
                    }
                });
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

                        liveXr = param.args[0];
                        lastParentId = param.args[2];
                        lastRefs = param.args[3];
                        lastSv8 = param.args[7];
                        lastEw1 = param.args[8];
                        lastYg2 = param.args[9];

                        Log.i(TAG, "DEEPSEEK_NATIVE_CONTEXT_CAPTURED xr=" + identity(liveXr)
                                + " sv8=" + identity(lastSv8)
                                + " ew1=" + identity(lastEw1)
                                + " yg2Class=" + className(lastYg2)
                                + " parentPresent=" + (lastParentId != null)
                                + " refsClass=" + className(lastRefs));
                    }
                });
    }

    private static String identity(Object value) {
        return value == null ? "null" : value.getClass().getSimpleName() + "@" + System.identityHashCode(value);
    }

    private static String className(Object value) {
        return value == null ? "null" : value.getClass().getName();
    }
}
