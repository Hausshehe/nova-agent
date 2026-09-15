package com.hausshehe.nova;

import android.util.Log;

import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

/**
 * DeepSeek in-process response-stream probe.
 *
 * Vector has already proven that Nova can execute inside DeepSeek. This probe
 * stays above the network layer and observes the semantic response fragment
 * mutation points discovered in DeepSeek 2.5.1:
 * n63.b(String, nx4, n62) for APPEND and
 * n63.j(String, nx4, r21, n62) for SET.
 */
public final class DeepSeekHookProbe implements IXposedHookLoadPackage {
    private static final String TAG = "NovaDeepSeekHook";
    private static final String TARGET_PACKAGE = "com.deepseek.chat";
    private static final String RESPONSE_FRAGMENT = "n63";
    private static final int PREVIEW_LIMIT = 96;
    private static final DeepSeekResponseCollector RESPONSE_COLLECTOR =
            new DeepSeekResponseCollector();

    @Override
    public void handleLoadPackage(XC_LoadPackage.LoadPackageParam lpparam) {
        if (!TARGET_PACKAGE.equals(lpparam.packageName)) {
            return;
        }

        Log.i(TAG, "DEEPSEEK_HOOK_LOADED package=" + lpparam.packageName
                + " process=" + lpparam.processName);

        RESPONSE_COLLECTOR.setListener(new DeepSeekResponseCollector.Listener() {
            @Override
            public void onResponseStarted(String type, int id) {
                Log.i(TAG, "DEEPSEEK_RESPONSE_STARTED type=" + type + " id=" + id);
            }

            @Override
            public void onResponseDelta(String type, int id, String delta) {
                Log.i(TAG, "DEEPSEEK_RESPONSE_DELTA type=" + type
                        + " id=" + id + " delta=" + preview(delta));
            }

            @Override
            public void onResponseReplaced(String type, int id, String text) {
                Log.i(TAG, "DEEPSEEK_RESPONSE_REPLACED type=" + type
                        + " id=" + id + " length=" + text.length());
            }

            @Override
            public void onResponseFinished(String type, int id, String text) {
                Log.i(TAG, "DEEPSEEK_RESPONSE_FINISHED type=" + type
                        + " id=" + id + " length=" + text.length());
            }
        });

        try {
            hookAppend(lpparam.classLoader);
            hookSet(lpparam.classLoader);
            Log.i(TAG, "DEEPSEEK_RESPONSE_HOOKS_INSTALLED class=" + RESPONSE_FRAGMENT);
        } catch (Throwable t) {
            Log.e(TAG, "DEEPSEEK_RESPONSE_HOOKS_FAILED", t);
        }
    }

    private static void hookAppend(ClassLoader classLoader) throws ClassNotFoundException {
        Class<?> n63 = XposedHelpers.findClass(RESPONSE_FRAGMENT, classLoader);
        Class<?> nx4 = XposedHelpers.findClass("nx4", classLoader);
        Class<?> n62 = XposedHelpers.findClass("n62", classLoader);

        XposedHelpers.findAndHookMethod(
                n63,
                "b",
                String.class,
                nx4,
                n62,
                new ResponseHook("APPEND"));
    }

    private static void hookSet(ClassLoader classLoader) throws ClassNotFoundException {
        Class<?> n63 = XposedHelpers.findClass(RESPONSE_FRAGMENT, classLoader);
        Class<?> nx4 = XposedHelpers.findClass("nx4", classLoader);
        Class<?> r21 = XposedHelpers.findClass("r21", classLoader);
        Class<?> n62 = XposedHelpers.findClass("n62", classLoader);

        XposedHelpers.findAndHookMethod(
                n63,
                "j",
                String.class,
                nx4,
                r21,
                n62,
                new ResponseHook("SET"));
    }

    private static String preview(String text) {
        String value = text == null ? "" : text.replace('\n', ' ').replace('\r', ' ');
        if (value.length() > PREVIEW_LIMIT) {
            return value.substring(0, PREVIEW_LIMIT) + "...";
        }
        return value;
    }

    private static final class ResponseHook extends XC_MethodHook {
        private final String operation;

        ResponseHook(String operation) {
            this.operation = operation;
        }

        @Override
        protected void afterHookedMethod(MethodHookParam param) {
            try {
                Object fragment = param.thisObject;
                String type = String.valueOf(XposedHelpers.getObjectField(fragment, "a"));
                int id = XposedHelpers.getIntField(fragment, "b");
                String text = String.valueOf(XposedHelpers.callMethod(fragment, "g"));

                if ("APPEND".equals(operation)) {
                    RESPONSE_COLLECTOR.append(type, id, text);
                } else {
                    RESPONSE_COLLECTOR.replace(type, id, text);
                }

                Log.i(TAG, "DEEPSEEK_RESPONSE_FRAGMENT operation=" + operation
                        + " type=" + type
                        + " id=" + id
                        + " length=" + text.length()
                        + " preview=" + preview(text));
            } catch (Throwable t) {
                Log.e(TAG, "DEEPSEEK_RESPONSE_FRAGMENT_LOG_FAILED", t);
            }
        }
    }
}
