package com.hausshehe.nova;

import android.util.Log;

import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

/**
 * Metadata-only probe for DeepSeek's live b18.v native send entry.
 * It observes argument shape and object identity without logging prompt text
 * or invoking/modifying the request.
 */
public final class DeepSeekB18SendProbe implements IXposedHookLoadPackage {
    private static final String TAG = "NovaDeepSeekHook";
    private static final String TARGET_PACKAGE = "com.deepseek.chat";

    @Override
    public void handleLoadPackage(XC_LoadPackage.LoadPackageParam lpparam) {
        if (!TARGET_PACKAGE.equals(lpparam.packageName)) {
            return;
        }

        try {
            Class<?> b18 = XposedHelpers.findClass("b18", lpparam.classLoader);
            Class<?> xr = XposedHelpers.findClass("xr", lpparam.classLoader);
            Class<?> sv8 = XposedHelpers.findClass("sv8", lpparam.classLoader);
            Class<?> ew1 = XposedHelpers.findClass("ew1", lpparam.classLoader);
            Class<?> yg2 = XposedHelpers.findClass("yg2", lpparam.classLoader);

            XposedHelpers.findAndHookMethod(
                    b18,
                    "v",
                    xr,
                    String.class,
                    Integer.class,
                    java.util.List.class,
                    boolean.class,
                    boolean.class,
                    String.class,
                    sv8,
                    ew1,
                    yg2,
                    new B18SendHook());

            Log.i(TAG, "DEEPSEEK_B18_SEND_HOOK_INSTALLED class=b18 method=v");
        } catch (Throwable t) {
            Log.e(TAG, "DEEPSEEK_B18_SEND_HOOK_INSTALL_FAILED", t);
        }
    }

    private static final class B18SendHook extends XC_MethodHook {
        @Override
        protected void beforeHookedMethod(MethodHookParam param) {
            try {
                Object b18 = param.thisObject;
                Object xr = param.args[0];
                Object prompt = param.args[1];
                Object parentId = param.args[2];
                Object refs = param.args[3];
                Object thinking = param.args[4];
                Object search = param.args[5];
                Object audioId = param.args[6];
                Object sv8 = param.args[7];
                Object ew1 = param.args[8];
                Object yg2 = param.args[9];

                int refsSize = refs instanceof java.util.Collection
                        ? ((java.util.Collection<?>) refs).size() : -1;
                boolean realSend = stringLength(prompt) > 0
                        && "ap1".equals(className(yg2));

                StringBuilder line = new StringBuilder()
                        .append("DEEPSEEK_B18_SEND_ENTRY")
                        .append(" b18Identity=").append(System.identityHashCode(b18))
                        .append(" xrClass=").append(className(xr))
                        .append(" xrIdentity=").append(identity(xr))
                        .append(" promptLength=").append(stringLength(prompt))
                        .append(" parentIdClass=").append(className(parentId))
                        .append(" parentIdPresent=").append(parentId != null)
                        .append(" refsClass=").append(className(refs))
                        .append(" refsSize=").append(refsSize)
                        .append(" thinking=").append(thinking)
                        .append(" search=").append(search)
                        .append(" audioIdPresent=").append(audioId != null)
                        .append(" sv8Class=").append(className(sv8))
                        .append(" sv8Identity=").append(identity(sv8))
                        .append(" ew1Class=").append(className(ew1))
                        .append(" ew1Identity=").append(identity(ew1))
                        .append(" yg2Class=").append(className(yg2))
                        .append(" yg2Identity=").append(identity(yg2));
                Log.i(TAG, line.toString());

                if (realSend) {
                    StackTraceElement[] stack = Thread.currentThread().getStackTrace();
                    StringBuilder callers = new StringBuilder("DEEPSEEK_B18_SEND_CALLERS");
                    int emitted = 0;
                    for (StackTraceElement frame : stack) {
                        String className = frame.getClassName();
                        if (className.equals(Thread.class.getName())
                                || className.startsWith("de.robv.android.xposed.")) {
                            continue;
                        }
                        callers.append(' ')
                                .append(className)
                                .append('#')
                                .append(frame.getMethodName())
                                .append(':')
                                .append(frame.getLineNumber());
                        emitted++;
                        if (emitted >= 12) {
                            break;
                        }
                    }
                    Log.i(TAG, callers.toString());
                }
            } catch (Throwable t) {
                Log.e(TAG, "DEEPSEEK_B18_SEND_PROBE_FAILED", t);
            }
        }
    }

    private static String className(Object value) {
        return value == null ? "null" : value.getClass().getName();
    }

    private static int identity(Object value) {
        return value == null ? -1 : System.identityHashCode(value);
    }

    private static int stringLength(Object value) {
        return value == null ? -1 : String.valueOf(value).length();
    }
}
