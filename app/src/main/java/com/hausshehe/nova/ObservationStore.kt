package com.hausshehe.nova

import android.view.accessibility.AccessibilityNodeInfo
import java.util.concurrent.atomic.AtomicLong

object ObservationStore {
    private val sequence = AtomicLong(0)

    @Volatile
    private var latest: UiSnapshot = UiSnapshot(0, emptyList())

    fun update(root: AccessibilityNodeInfo?) {
        if (root == null) return
        val elements = mutableListOf<UiElementSnapshot>()
        collect(root, elements, "0")
        latest = UiSnapshot(sequence.incrementAndGet(), elements)
    }

    fun current(): UiSnapshot = latest

    private fun collect(
        node: AccessibilityNodeInfo,
        out: MutableList<UiElementSnapshot>,
        path: String
    ) {
        val resourceId = node.viewIdResourceName
        val stableId = resourceId?.takeIf { it.isNotBlank() } ?: "path:$path"

        out += UiElementSnapshot(
            id = stableId,
            text = node.text?.toString() ?: "",
            contentDescription = node.contentDescription?.toString() ?: "",
            clickable = node.isClickable,
            enabled = node.isEnabled
        )

        for (i in 0 until node.childCount) {
            node.getChild(i)?.let { child ->
                collect(child, out, "$path.$i")
                child.recycle()
            }
        }
    }
}

data class UiSnapshot(val observationId: Long, val elements: List<UiElementSnapshot>)

data class UiElementSnapshot(
    val id: String,
    val text: String,
    val contentDescription: String,
    val clickable: Boolean,
    val enabled: Boolean
)
