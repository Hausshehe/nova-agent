package com.hausshehe.nova;

import android.util.Log;

import java.lang.reflect.Field;

import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

/**
 * Metadata-only probe for DeepSeek's live kk1 -> np1 -> p41 -> b18 session chain.
 * It does not invoke or modify DeepSeek requests.
 *
 * G11 additionally traces construction of the native request-context helper
 * objects (sv8/ew1/yg2/ap1), and now records the fresh xr field state when the
 * live kk1 is resolved. Only metadata, sizes, identities and primitive values
 * are logged, never string contents.
 */
public final class DeepSeekKk1SessionProbe implements IXposedHookLoadPackage {
    private static final String TAG = "NovaDeepSeekHook";
    private static final String TARGET_PACKAGE = "com.deepseek.chat";

    @Override
    public void handleLoadPackage(XC_LoadPackage.LoadPackageParam lpparam) {
        if (!TARGET_PACKAGE.equals(lpparam.packageName)) {
            return;
        }

        try {
            Class<?> x05 = XposedHelpers.findClass("x05", lpparam.classLoader);
            Class<?> p35 = XposedHelpers.findClass("p35", lpparam.classLoader);
            Class<?> f5a = XposedHelpers.findClass("f5a", lpparam.classLoader);
            Class<?> pj2 = XposedHelpers.findClass("pj2", lpparam.classLoader);
            Class<?> g48 = XposedHelpers.findClass("g48", lpparam.classLoader);
            Class<?> kx3 = XposedHelpers.findClass("kx3", lpparam.classLoader);

            XposedHelpers.findAndHookMethod(
                    x05,
                    "K0",
                    p35,
                    f5a,
                    String.class,
                    pj2,
                    g48,
                    kx3,
                    new XC_MethodHook() {
                        @Override
                        protected void afterHookedMethod(MethodHookParam param) {
                            try {
                                Object kk1 = param.getResult();
                                if (kk1 == null || !"kk1".equals(kk1.getClass().getName())) {
                                    return;
                                }

                                Object d = XposedHelpers.getObjectField(kk1, "d");
                                Object zj1 = d == null ? null : XposedHelpers.callMethod(d, "getValue");
                                Object liveState = zj1 == null ? null : XposedHelpers.getObjectField(zj1, "c");
                                Object np1 = liveState != null && "np1".equals(liveState.getClass().getName())
                                        ? liveState
                                        : null;

                                Object p41 = XposedHelpers.getObjectField(kk1, "h");
                                Object b18 = p41 == null
                                        ? null
                                        : XposedHelpers.getObjectField(p41, "b");

                                Log.i(TAG,
                                        "DEEPSEEK_KK1_SESSION_CHAIN"
                                                + " kk1Identity=" + System.identityHashCode(kk1)
                                                + " np1Identity=" + (np1 == null ? -1 : System.identityHashCode(np1))
                                                + " p41Class=" + (p41 == null ? "null" : p41.getClass().getName())
                                                + " p41Identity=" + (p41 == null ? -1 : System.identityHashCode(p41))
                                                + " b18Class=" + (b18 == null ? "null" : b18.getClass().getName())
                                                + " b18Identity=" + (b18 == null ? -1 : System.identityHashCode(b18)));

                                if (np1 != null) {
                                    Object xr = XposedHelpers.callMethod(np1, "M");
                                    logXrFields(xr, "DEEPSEEK_FRESH_XR_FIELDS");
                                }
                            } catch (Throwable t) {
                                Log.e(TAG, "DEEPSEEK_KK1_SESSION_CHAIN_FAILED", t);
                            }
                        }
                    });

            hookConstructors(lpparam.classLoader);
            Log.i(TAG, "DEEPSEEK_KK1_SESSION_HOOK_INSTALLED class=x05 method=K0");
        } catch (Throwable t) {
            Log.e(TAG, "DEEPSEEK_KK1_SESSION_HOOK_INSTALL_FAILED", t);
        }
    }

    private static void logXrFields(Object xr, String prefix) {
        if (xr == null) {
            Log.i(TAG, prefix + " null");
            return;
        }
        try {
            Field[] fields = xr.getClass().getDeclaredFields();
            StringBuilder line = new StringBuilder(prefix)
                    .append(" xrIdentity=").append(System.identityHashCode(xr));
            for (Field field : fields) {
                try {
                    field.setAccessible(true);
                    Object value = field.get(xr);
                    line.append(' ')
                            .append(field.getName()).append('=')
                            .append(describeFieldValue(value));
                } catch (Throwable t) {
                    line.append(' ').append(field.getName()).append("=<unreadable:")
                            .append(t.getClass().getSimpleName()).append('>');
                }
            }
            Log.i(TAG, line.toString());
        } catch (Throwable t) {
            Log.e(TAG, prefix + "_FAILED", t);
        }
    }

    private static String describeFieldValue(Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof String) {
            return "String(length=" + ((String) value).length() + ")";
        }
        if (value instanceof Number || value instanceof Boolean || value instanceof Character) {
            return value.getClass().getSimpleName() + "(" + value + ")";
        }
        if (value instanceof java.util.Map) {
            return value.getClass().getName() + "(size=" + ((java.util.Map<?, ?>) value).size()
                    + ",identity=" + System.identityHashCode(value) + ")";
        }
        if (value instanceof java.util.Collection) {
            return value.getClass().getName() + "(size=" + ((java.util.Collection<?>) value).size()
                    + ",identity=" + System.identityHashCode(value) + ")";
        }
        return value.getClass().getName() + "(identity=" + System.identityHashCode(value) + ")";
    }

    private static void hookConstructors(ClassLoader classLoader) throws ClassNotFoundException {
        hookConstructorsFor("sv8", classLoader);
        hookConstructorsFor("ew1", classLoader);
        hookConstructorsFor("yg2", classLoader);
        hookConstructorsFor("ap1", classLoader);
    }

    private static void hookConstructorsFor(String className, ClassLoader classLoader)
            throws ClassNotFoundException {
        Class<?> type = XposedHelpers.findClass(className, classLoader);
        XposedBridge.hookAllConstructors(type, new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                try {
                    Object instance = param.thisObject;
                    StackTraceElement[] stack = Thread.currentThread().getStackTrace();
                    StringBuilder callers = new StringBuilder("DEEPSEEK_CONTEXT_CONSTRUCTED")
                            .append(" class=").append(className)
                            .append(" identity=").append(System.identityHashCode(instance));
                    int emitted = 0;
                    for (StackTraceElement frame : stack) {
                        String owner = frame.getClassName();
                        if (owner.equals(Thread.class.getName())
                                || owner.startsWith("de.robv.android.xposed.")) {
                            continue;
                        }
                        callers.append(' ')
                                .append(owner)
                                .append('#')
                                .append(frame.getMethodName())
                                .append(':')
                                .append(frame.getLineNumber());
                        emitted++;
                        if (emitted >= 8) {
                            break;
                        }
                    }
                    Log.i(TAG, callers.toString());
                } catch (Throwable t) {
                    Log.e(TAG, "DEEPSEEK_CONTEXT_CONSTRUCTOR_TRACE_FAILED class=" + className, t);
                }
            }
        });
        Log.i(TAG, "DEEPSEEK_CONTEXT_CONSTRUCTOR_HOOK_INSTALLED class=" + className);
    }
}
