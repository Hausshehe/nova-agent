package com.hausshehe.nova;

import android.util.Log;

import de.robv.android.xposed.IXposedHookZygoteInit;

public final class VectorZygoteProbe implements IXposedHookZygoteInit {
    private static final String TAG = "NovaVectorZygote";

    @Override
    public void initZygote(StartupParam startupParam) {
        Log.i(TAG, "VECTOR_ZYGOTE_INIT process=" + startupParam.modulePath);
    }
}
