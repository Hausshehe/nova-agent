package com.hausshehe.nova;

import android.util.Log;

import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

/**
 * DeepSeek 2.5.3 runtime trace.
 *
 * This probe is observation-only. It maps the live qi1 -> np6 -> xh1 -> sj1
 * request path without invoking or modifying DeepSeek requests.
 */
public final class DeepSeek253RuntimeProbe implements IXposedHookLoadPackage {
    private static final String TAG = "NovaDeepSeek253";
    private static final String TARGET_PACKAGE = "com.deepseek.chat";

    private static volatile Object liveQi1;
    private static volatile Object liveNp6;
    private static volatile Object liveSession;

    @Override
    public void handleLoadPackage(XC_LoadPackage.LoadPackageParam lpparam) {
        if (!TARGET_PACKAGE.equals(lpparam.packageName)) {
            return;
        }

        Log.i(TAG, "DS253_TRACE_LOADED process=" + lpparam.processName);

        try {
            ClassLoader cl = lpparam.classLoader;
            hookQi1(cl);
            hookNp6(cl);
            hookXh1(cl);
            hookNativeCompletionPath(cl);
            Log.i(TAG, "DS253_TRACE_INSTALLED");
        } catch (Throwable t) {
            Log.e(TAG, "DS253_TRACE_INSTALL_FAILED", t);
        }
    }

    private static void hookQi1(ClassLoader cl) throws ClassNotFoundException {
        Class<?> qi1 = XposedHelpers.findClass("qi1", cl);

        XposedBridge.hookAllConstructors(qi1, new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                try {
                    liveQi1 = param.thisObject;
                    Object np6 = XposedHelpers.getObjectField(param.thisObject, "b");
                    liveNp6 = np6;

                    Log.i(TAG, "DS253_QI1_CREATED qi1=" + identity(param.thisObject)
                            + " np6=" + identity(np6));
                    logObjectFields("DS253_QI1_FIELDS", param.thisObject,
                            new String[]{"a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m"});
                } catch (Throwable t) {
                    Log.e(TAG, "DS253_QI1_CREATE_LOG_FAILED", t);
                }
            }
        });

        XposedBridge.hookAllMethods(qi1, "a", new XC_MethodHook() {
            @Override
            protected void beforeHookedMethod(MethodHookParam param) {
                try {
                    if (param.args.length > 0 && param.args[0] != null
                            && "is".equals(param.args[0].getClass().getName())) {
                        liveSession = param.args[0];
                        Log.i(TAG, "DS253_SESSION_RECEIVED session="
                                + identity(liveSession)
                                + " qi1=" + identity(param.thisObject)
                                + " np6=" + identity(liveNp6));
                    }
                } catch (Throwable t) {
                    Log.e(TAG, "DS253_SESSION_LOG_FAILED", t);
                }
            }
        });

        Log.i(TAG, "DS253_QI1_HOOKS_INSTALLED");
    }

    private static void hookNp6(ClassLoader cl) throws ClassNotFoundException {
        Class<?> np6 = XposedHelpers.findClass("np6", cl);

        XposedBridge.hookAllMethods(np6, "k", new XC_MethodHook() {
            @Override
            protected void beforeHookedMethod(MethodHookParam param) {
                try {
                    liveNp6 = param.thisObject;

                    StringBuilder args = new StringBuilder();
                    for (int i = 0; i < param.args.length; i++) {
                        if (i > 0) args.append(" | ");
                        Object value = param.args[i];
                        args.append(i).append("=")
                                .append(value == null ? "null" : value.getClass().getName());
                        if (i == 1 || i == 6) {
                            args.append(":").append(preview(value));
                        }
                    }

                    Log.i(TAG, "DS253_NP6_K_ENTER receiver="
                            + identity(param.thisObject)
                            + " args=" + args
                            + " liveSession=" + identity(liveSession));

                    logObjectFields("DS253_NP6_FIELDS", param.thisObject,
                            new String[]{"a", "b", "c", "d", "e", "f"});
                    logCallerStack("DS253_NP6_K_STACK");

                    if (param.args.length > 0 && param.args[0] != null) {
                        logObjectFields("DS253_SESSION_FIELDS", param.args[0],
                                new String[]{"a", "e", "n", "o", "p", "r"});
                    }
                } catch (Throwable t) {
                    Log.e(TAG, "DS253_NP6_K_LOG_FAILED", t);
                }
            }

            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                try {
                    Log.i(TAG, "DS253_NP6_K_EXIT result="
                            + (param.getResult() == null
                            ? "null" : param.getResult().getClass().getName()));
                } catch (Throwable t) {
                    Log.e(TAG, "DS253_NP6_K_EXIT_LOG_FAILED", t);
                }
            }
        });

        Log.i(TAG, "DS253_NP6_K_HOOK_INSTALLED");
    }

    private static void hookXh1(ClassLoader cl) throws ClassNotFoundException {
        Class<?> xh1 = XposedHelpers.findClass("xh1", cl);

        XposedBridge.hookAllConstructors(xh1, new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                try {
                    Object request = param.thisObject;
                    Log.i(TAG, "DS253_XH1_CREATED request=" + identity(request)
                            + " argCount=" + param.args.length);
                    logObjectFields("DS253_XH1_FIELDS", request,
                            new String[]{"e", "f", "g", "h", "i", "j", "k", "l", "m", "n"});
                } catch (Throwable t) {
                    Log.e(TAG, "DS253_XH1_LOG_FAILED", t);
                }
            }
        });

        Log.i(TAG, "DS253_XH1_HOOK_INSTALLED");
    }

    private static void hookNativeCompletionPath(ClassLoader cl) throws ClassNotFoundException {
        hookMethodTrace(cl, "np6", "A", "DS253_NP6_A");
        hookMethodTrace(cl, "ra2", "e", "DS253_RA2_E");
        hookMethodTrace(cl, "ra2", "h", "DS253_RA2_H");
        hookMethodTrace(cl, "ar1", "k", "DS253_AR1_K");
        hookZa2Result(cl);
        hookConstructorsTrace(cl, "xa2", "DS253_XA2_CREATED",
                new String[]{"a", "b", "c", "d", "e", "f"});
        hookConstructorsTrace(cl, "qh1", "DS253_QH1_CREATED",
                new String[]{"a", "b", "c", "d"});
        hookConstructorsTrace(cl, "t47", "DS253_T47_CREATED",
                new String[]{"a", "b"},
                true);
        hookConstructorsTrace(cl, "wa2", "DS253_WA2_CREATED",
                new String[]{"a", "b", "c", "d", "e", "f", "g"});
        Log.i(TAG, "DS253_NATIVE_COMPLETION_HOOKS_INSTALLED");
    }

    private static void hookZa2Result(ClassLoader cl) throws ClassNotFoundException {
        Class<?> za2 = XposedHelpers.findClass("za2", cl);
        XposedBridge.hookAllMethods(za2, "A", new XC_MethodHook() {
            @Override
            protected void beforeHookedMethod(MethodHookParam param) {
                try {
                    Object wa2 = XposedHelpers.getObjectField(param.thisObject, "f");
                    Object result = wa2 == null ? null : XposedHelpers.getObjectField(wa2, "a");
                    Log.i(TAG, "DS253_ZA2_A_ENTER wa2=" + identity(wa2)
                            + " result=" + identity(result));
                    if (result != null && "t47".equals(result.getClass().getName())) {
                        logObjectFields("DS253_ZA2_T47", result, new String[]{"a", "b"});
                    }
                    logObjectFields("DS253_ZA2_WA2", wa2,
                            new String[]{"a", "b", "c", "d", "e", "f", "g"});
                } catch (Throwable t) {
                    Log.e(TAG, "DS253_ZA2_A_LOG_FAILED", t);
                }
            }
        });
        Log.i(TAG, "DS253_ZA2_A_HOOK_INSTALLED class=za2 method=A");
    }

    private static void hookConstructorsTrace(ClassLoader cl, String className, String prefix,
            String[] fields) throws ClassNotFoundException {
        hookConstructorsTrace(cl, className, prefix, fields, false);
    }

    private static void hookConstructorsTrace(ClassLoader cl, String className, String prefix,
            String[] fields, boolean traceConstructorArgs) throws ClassNotFoundException {
        Class<?> target = XposedHelpers.findClass(className, cl);
        XposedBridge.hookAllConstructors(target, new XC_MethodHook() {
            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                try {
                    Log.i(TAG, prefix + " object=" + identity(param.thisObject)
                            + " argTypes=" + argumentTypes(param.args));
                    logObjectFields(prefix + "_FIELDS", param.thisObject, fields);
                    if (traceConstructorArgs) {
                        Log.i(TAG, prefix + "_ARGS " + argumentPreviews(param.args));
                        logCallerStack(prefix + "_STACK");
                    }
                } catch (Throwable t) {
                    Log.e(TAG, prefix + "_LOG_FAILED", t);
                }
            }
        });
        Log.i(TAG, prefix + "_HOOK_INSTALLED class=" + className);
    }

    private static void hookMethodTrace(ClassLoader cl, String className, String methodName, String prefix)
            throws ClassNotFoundException {
        Class<?> target = XposedHelpers.findClass(className, cl);
        XposedBridge.hookAllMethods(target, methodName, new XC_MethodHook() {
            @Override
            protected void beforeHookedMethod(MethodHookParam param) {
                try {
                    Log.i(TAG, prefix + "_ENTER receiver=" + identity(param.thisObject)
                            + " args=" + argumentTypes(param.args));
                } catch (Throwable t) {
                    Log.e(TAG, prefix + "_ENTER_LOG_FAILED", t);
                }
            }

            @Override
            protected void afterHookedMethod(MethodHookParam param) {
                try {
                    Throwable error = param.getThrowable();
                    if (error != null) {
                        Log.e(TAG, prefix + "_THROW " + error.getClass().getName()
                                + ":" + String.valueOf(error.getMessage()));
                    } else {
                        Object result = param.getResult();
                        Log.i(TAG, prefix + "_EXIT result=" + identity(result));
                    }
                } catch (Throwable t) {
                    Log.e(TAG, prefix + "_EXIT_LOG_FAILED", t);
                }
            }
        });
        Log.i(TAG, prefix + "_HOOK_INSTALLED class=" + className + " method=" + methodName);
    }

    private static String argumentPreviews(Object[] args) {
        if (args == null) return "null";
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < args.length; i++) {
            if (i > 0) out.append(" | ");
            out.append(i).append("=").append(preview(args[i]));
        }
        return out.toString();
    }

    private static String argumentTypes(Object[] args) {
        if (args == null) return "null";
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < args.length; i++) {
            if (i > 0) out.append(" | ");
            Object value = args[i];
            out.append(i).append("=")
                    .append(value == null ? "null" : value.getClass().getName());
        }
        return out.toString();
    }

    private static void logObjectFields(String prefix, Object value, String[] fields) {
        if (value == null) {
            Log.i(TAG, prefix + " null");
            return;
        }

        StringBuilder out = new StringBuilder(prefix)
                .append(" object=").append(identity(value));

        for (String field : fields) {
            try {
                Object fieldValue = XposedHelpers.getObjectField(value, field);
                out.append(" ").append(field).append("=")
                        .append(preview(fieldValue));
            } catch (Throwable ignored) {
            }
        }

        Log.i(TAG, out.toString());
    }

    private static void logCallerStack(String prefix) {
        try {
            StackTraceElement[] stack = Thread.currentThread().getStackTrace();
            StringBuilder out = new StringBuilder(prefix);
            int emitted = 0;
            for (StackTraceElement frame : stack) {
                String name = frame.getClassName();
                if (name.equals(Thread.class.getName())
                        || name.equals(DeepSeek253RuntimeProbe.class.getName())
                        || name.startsWith("de.robv.android.xposed.")) {
                    continue;
                }
                out.append(" ").append(frame.toString());
                if (++emitted >= 8) break;
            }
            Log.i(TAG, out.toString());
        } catch (Throwable t) {
            Log.e(TAG, prefix + "_FAILED", t);
        }
    }

    private static String preview(Object value) {
        if (value == null) return "null";
        String text = String.valueOf(value).replace('\n', ' ').replace('\r', ' ');
        if (text.length() > 160) {
            return text.substring(0, 160) + "...";
        }
        return text;
    }

    private static String identity(Object value) {
        return value == null
                ? "null"
                : value.getClass().getName() + "@"
                + Integer.toHexString(System.identityHashCode(value));
    }
}
