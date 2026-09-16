package com.hausshehe.nova;

import android.util.Log;

import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

/**
 * Metadata-only probe for DeepSeek's live kk1 -> np1 -> p41 -> b18 session chain.
 * It does not invoke or modify DeepSeek requests.
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
                            } catch (Throwable t) {
                                Log.e(TAG, "DEEPSEEK_KK1_SESSION_CHAIN_FAILED", t);
                            }
                        }
                    });

            Log.i(TAG, "DEEPSEEK_KK1_SESSION_HOOK_INSTALLED class=x05 method=K0");
        } catch (Throwable t) {
            Log.e(TAG, "DEEPSEEK_KK1_SESSION_HOOK_INSTALL_FAILED", t);
        }
    }
}
