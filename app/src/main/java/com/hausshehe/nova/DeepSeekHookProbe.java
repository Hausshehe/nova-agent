package com.hausshehe.nova;

import android.util.Log;

import org.json.JSONObject;

import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

/**
 * DeepSeek in-process response/request probe.
 *
 * Vector has already proven that Nova can execute inside DeepSeek. This probe
 * observes semantic response fragments, native SSE completion, the internal
 * request entry point, the construction of the concrete r51 request, and
 * resolution of DeepSeek's live kk1 ViewModel.
 * It does not modify or invoke DeepSeek requests.
 */
public final class DeepSeekHookProbe implements IXposedHookLoadPackage {
    private static final String TAG = "NovaDeepSeekHook";
    private static final String TARGET_PACKAGE = "com.deepseek.chat";
    private static final String RESPONSE_FRAGMENT = "n63";
    private static final String STREAM_DISPATCHER = "x21";
    private static final String STREAM_EVENT = "k09";
    private static final String REQUEST_DISPATCHER = "ir2";
    private static final String REQUEST_INTERFACE = "h21";
    private static final String REQUEST_MODEL = "r51";
    private static final int PREVIEW_LIMIT = 96;
    private static final DeepSeekResponseCollector RESPONSE_COLLECTOR = new DeepSeekResponseCollector();
    private static volatile int activeResponseId = -1;
    private static volatile Object liveKk1ViewModel;

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
                DeepSeekBridgeClient.sendStarted(type, id);
            }

            @Override
            public void onResponseDelta(String type, int id, String delta) {
                Log.i(TAG, "DEEPSEEK_RESPONSE_DELTA type=" + type
                        + " id=" + id + " delta=" + preview(delta));
                DeepSeekBridgeClient.sendDelta(type, id, delta);
            }

            @Override
            public void onResponseReplaced(String type, int id, String text) {
                Log.i(TAG, "DEEPSEEK_RESPONSE_REPLACED type=" + type
                        + " id=" + id + " length=" + text.length());
                DeepSeekBridgeClient.sendReplaced(type, id, text);
            }

            @Override
            public void onResponseFinished(String type, int id, String text) {
                Log.i(TAG, "DEEPSEEK_RESPONSE_FINISHED type=" + type
                        + " id=" + id + " length=" + text.length());
                DeepSeekBridgeClient.sendFinished(type, id, text);
            }
        });

        try {
            hookAppend(lpparam.classLoader);
            hookSet(lpparam.classLoader);
            hookStreamEvents(lpparam.classLoader);
            hookRequestEntryPoint(lpparam.classLoader);
            hookRequestConstruction(lpparam.classLoader);
            hookViewModelResolution(lpparam.classLoader);
            Log.i(TAG, "DEEPSEEK_RESPONSE_HOOKS_INSTALLED class=" + RESPONSE_FRAGMENT);
            Log.i(TAG, "DEEPSEEK_STREAM_EVENT_HOOK_INSTALLED class=" + STREAM_DISPATCHER);
            Log.i(TAG, "DEEPSEEK_REQUEST_HOOK_INSTALLED class=" + REQUEST_DISPATCHER);
            Log.i(TAG, "DEEPSEEK_REQUEST_CONSTRUCTION_HOOK_INSTALLED class=" + REQUEST_MODEL);
            Log.i(TAG, "DEEPSEEK_KK1_VM_HOOK_INSTALLED class=x05 method=K0");
        } catch (Throwable t) {
            Log.e(TAG, "DEEPSEEK_RESPONSE_HOOKS_FAILED", t);
        }
    }

    private static void hookViewModelResolution(ClassLoader classLoader) throws ClassNotFoundException {
        Class<?> x05 = XposedHelpers.findClass("x05", classLoader);
        Class<?> p35 = XposedHelpers.findClass("p35", classLoader);
        Class<?> f5a = XposedHelpers.findClass("f5a", classLoader);
        Class<?> pj2 = XposedHelpers.findClass("pj2", classLoader);
        Class<?> g48 = XposedHelpers.findClass("g48", classLoader);
        Class<?> kx3 = XposedHelpers.findClass("kx3", classLoader);

        XposedHelpers.findAndHookMethod(
                x05,
                "K0",
                p35,
                f5a,
                String.class,
                pj2,
                g48,
                kx3,
                new ViewModelResolutionHook());
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

    private static void hookStreamEvents(ClassLoader classLoader) throws ClassNotFoundException {
        Class<?> x21 = XposedHelpers.findClass(STREAM_DISPATCHER, classLoader);
        Class<?> k09 = XposedHelpers.findClass(STREAM_EVENT, classLoader);
        Class<?> zg2 = XposedHelpers.findClass("zg2", classLoader);

        XposedHelpers.findAndHookMethod(
                x21,
                "a",
                x21,
                k09,
                zg2,
                new StreamEventHook());
    }

    private static void hookRequestEntryPoint(ClassLoader classLoader) throws ClassNotFoundException {
        Class<?> ir2 = XposedHelpers.findClass(REQUEST_DISPATCHER, classLoader);
        Class<?> h21 = XposedHelpers.findClass(REQUEST_INTERFACE, classLoader);

        XposedHelpers.findAndHookMethod(
                ir2,
                "b",
                h21,
                Long.class,
                new RequestHook());
    }

    private static void hookRequestConstruction(ClassLoader classLoader) throws ClassNotFoundException {
        Class<?> r51 = XposedHelpers.findClass(REQUEST_MODEL, classLoader);
        XposedBridge.hookAllConstructors(r51, new RequestConstructionHook());
    }

    private static String preview(String text) {
        String value = text == null ? "" : text.replace('\n', ' ').replace('\r', ' ');
        if (value.length() > PREVIEW_LIMIT) {
            return value.substring(0, PREVIEW_LIMIT) + "...";
        }
        return value;
    }

    private static int stringLength(Object value) {
        return value == null ? -1 : String.valueOf(value).length();
    }

    private static String fieldSummary(Object request) {
        try {
            Object a = XposedHelpers.getObjectField(request, "a");
            Object b = XposedHelpers.getObjectField(request, "b");
            Object c = XposedHelpers.getObjectField(request, "c");
            Object d = XposedHelpers.getObjectField(request, "d");
            Object e = XposedHelpers.getObjectField(request, "e");
            Object f = XposedHelpers.getObjectField(request, "f");
            Object g = XposedHelpers.getObjectField(request, "g");
            Object h = XposedHelpers.getObjectField(request, "h");
            Object i = XposedHelpers.getObjectField(request, "i");
            Object j = XposedHelpers.getObjectField(request, "j");
            return "aLen=" + stringLength(a)
                    + " b=" + b
                    + " cLen=" + stringLength(c)
                    + " dClass=" + (d == null ? "null" : d.getClass().getName())
                    + " e=" + e
                    + " f=" + f
                    + " gLen=" + stringLength(g)
                    + " h=" + h
                    + " i=" + i
                    + " j=" + j;
        } catch (Throwable t) {
            return "fieldSummaryError=" + t.getClass().getSimpleName();
        }
    }

    private static final class ViewModelResolutionHook extends XC_MethodHook {
        @Override
        protected void afterHookedMethod(MethodHookParam param) {
            try {
                Object key = param.args.length > 0 ? param.args[0] : null;
                if (key == null) {
                    return;
                }

                String keyName = String.valueOf(XposedHelpers.callMethod(key, "b"));
                if (!keyName.contains("kk1")) {
                    return;
                }

                Object result = param.getResult();
                if (result == null) {
                    Log.i(TAG, "DEEPSEEK_KK1_VM_RESOLVED key=" + keyName
                            + " resultClass=null identity=-1");
                    return;
                }

                liveKk1ViewModel = result;
                Object currentXr = XposedHelpers.callMethod(result, "m");
                Log.i(TAG, "DEEPSEEK_KK1_VM_RESOLVED key=" + keyName
                        + " resultClass=" + result.getClass().getName()
                        + " identity=" + System.identityHashCode(result)
                        + " currentXrClass="
                        + (currentXr == null ? "null" : currentXr.getClass().getName())
                        + " currentXrIdentity="
                        + (currentXr == null ? -1 : System.identityHashCode(currentXr)));
            } catch (Throwable t) {
                Log.e(TAG, "DEEPSEEK_KK1_VM_RESOLUTION_FAILED", t);
            }
        }
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

    private static final class StreamEventHook extends XC_MethodHook {
        @Override
        protected void beforeHookedMethod(MethodHookParam param) {
            try {
                Object event = param.args.length > 1 ? param.args[1] : null;
                if (event == null) {
                    Log.i(TAG, "DEEPSEEK_STREAM_EVENT event=null");
                    return;
                }

                Object firstValue = null;
                Object secondValue = null;
                try {
                    firstValue = XposedHelpers.getObjectField(event, "a");
                } catch (Throwable ignored) {
                }
                try {
                    secondValue = XposedHelpers.getObjectField(event, "b");
                } catch (Throwable ignored) {
                }

                String first = firstValue == null ? null : String.valueOf(firstValue);
                String second = secondValue == null ? null : String.valueOf(secondValue);
                Log.i(TAG, "DEEPSEEK_STREAM_EVENT first=" + preview(first)
                        + " second=" + preview(second));

                handleCompletionSignal(first, second);
            } catch (Throwable t) {
                Log.e(TAG, "DEEPSEEK_STREAM_EVENT_LOG_FAILED", t);
            }
        }

        private static void handleCompletionSignal(String first, String second) {
            if (second == null || second.isEmpty()) {
                return;
            }

            try {
                JSONObject payload = new JSONObject(second);
                if (!"response/status".equals(payload.optString("p"))
                        || !"SET".equals(payload.optString("o"))
                        || !"FINISHED".equals(payload.optString("v"))) {
                    if ("ready".equals(first)) {
                        activeResponseId = payload.optInt("response_message_id", -1);
                    }
                    return;
                }

                int responseId = activeResponseId;
                if (responseId >= 0) {
                    Log.i(TAG, "DEEPSEEK_RESPONSE_FINISH_SIGNAL id=" + responseId);
                    RESPONSE_COLLECTOR.finish("RESPONSE", responseId);
                    activeResponseId = -1;
                } else {
                    Log.w(TAG, "DEEPSEEK_RESPONSE_FINISH_SIGNAL_WITHOUT_ID");
                }
            } catch (Throwable ignored) {
            }
        }
    }

    private static final class RequestHook extends XC_MethodHook {
        @Override
        protected void beforeHookedMethod(MethodHookParam param) {
            try {
                Object request = param.args.length > 0 ? param.args[0] : null;
                Object timeout = param.args.length > 1 ? param.args[1] : null;
                if (request == null) {
                    Log.i(TAG, "DEEPSEEK_REQUEST_ENTRY request=null timeout=" + timeout);
                    return;
                }

                Log.i(TAG, "DEEPSEEK_REQUEST_ENTRY requestClass="
                        + request.getClass().getName()
                        + " receiverClass="
                        + (param.thisObject == null ? "null" : param.thisObject.getClass().getName())
                        + " timeout=" + timeout
                        + " " + fieldSummary(request));
            } catch (Throwable t) {
                Log.e(TAG, "DEEPSEEK_REQUEST_ENTRY_LOG_FAILED", t);
            }
        }
    }

    private static final class RequestConstructionHook extends XC_MethodHook {
        @Override
        protected void afterHookedMethod(MethodHookParam param) {
            try {
                Object request = param.thisObject;
                StringBuilder args = new StringBuilder();
                for (int index = 0; index < param.args.length; index++) {
                    if (index > 0) {
                        args.append(',');
                    }
                    Object value = param.args[index];
                    args.append(index).append('=')
                            .append(value == null ? "null" : value.getClass().getName());
                }
                Log.i(TAG, "DEEPSEEK_REQUEST_CONSTRUCTED class="
                        + request.getClass().getName()
                        + " argTypes=[" + args + "] "
                        + fieldSummary(request));

                StackTraceElement[] stack = new Throwable().getStackTrace();
                StringBuilder callerTrace = new StringBuilder();
                int emitted = 0;
                for (StackTraceElement frame : stack) {
                    String className = frame.getClassName();
                    if (className.equals(DeepSeekHookProbe.class.getName())
                            || className.startsWith("de.robv.android.xposed.")) {
                        continue;
                    }
                    if (emitted > 0) {
                        callerTrace.append(" <- ");
                    }
                    callerTrace.append(className)
                            .append('#').append(frame.getMethodName())
                            .append(':').append(frame.getLineNumber());
                    emitted++;
                    if (emitted >= 8) {
                        break;
                    }
                }
                Log.i(TAG, "DEEPSEEK_REQUEST_CONSTRUCTION_CALLERS " + callerTrace);
            } catch (Throwable t) {
                Log.e(TAG, "DEEPSEEK_REQUEST_CONSTRUCTION_LOG_FAILED", t);
            }
        }
    }
}
