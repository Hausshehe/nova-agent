package com.hausshehe.nova

import android.service.voice.VoiceInteractionService
import android.util.Log

class NovaVoiceInteractionService : VoiceInteractionService() {
    override fun onReady() {
        super.onReady()
        Log.i(TAG, "NOVA_VOICE_INTERACTION_READY")
    }

    override fun onShutdown() {
        Log.i(TAG, "NOVA_VOICE_INTERACTION_SHUTDOWN")
        super.onShutdown()
    }

    private companion object {
        const val TAG = "NovaVoiceService"
    }
}