package com.hausshehe.nova

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

class NovaAccessibilityService : AccessibilityService() {
    companion object {
        @Volatile
        var instance: NovaAccessibilityService? = null
            private set
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        ObservationStore.update(rootInActiveWindow)
        BridgeServer.start(this)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        ObservationStore.update(rootInActiveWindow)
    }

    override fun onInterrupt() = Unit

    fun clickNode(node: AccessibilityNodeInfo): Boolean =
        node.isClickable && node.performAction(AccessibilityNodeInfo.ACTION_CLICK)

    override fun onDestroy() {
        if (instance === this) instance = null
        super.onDestroy()
    }
}
