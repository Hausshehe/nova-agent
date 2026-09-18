package com.hausshehe.nova

import android.graphics.Rect
import android.view.accessibility.AccessibilityNodeInfo
import java.util.concurrent.atomic.AtomicLong

object ObservationStore {
    private val sequence = AtomicLong(0)

    @Volatile
    private var latest: UiSnapshot = UiSnapshot(0, "", "", emptyList())

    fun update(root: AccessibilityNodeInfo?) {
        if (root == null) return
        val elements = mutableListOf<UiElementSnapshot>()
        val resourceIdCounts = mutableMapOf<String, Int>()
        countResourceIds(root, resourceIdCounts)
        collect(root, elements, "0", resourceIdCounts)
        val packageName = root.packageName?.toString() ?: ""
        val className = root.className?.toString() ?: ""
        latest = UiSnapshot(
            observationId = sequence.incrementAndGet(),
            packageName = packageName,
            activity = className,
            elements = elements
        )
    }

    fun current(): UiSnapshot = latest

    private fun countResourceIds(
        node: AccessibilityNodeInfo,
        counts: MutableMap<String, Int>,
    ) {
        node.viewIdResourceName
            ?.takeIf { it.isNotBlank() }
            ?.let { counts[it] = (counts[it] ?: 0) + 1 }

        for (i in 0 until node.childCount) {
            node.getChild(i)?.let { child ->
                countResourceIds(child, counts)
                child.recycle()
            }
        }
    }

    private fun collect(
        node: AccessibilityNodeInfo,
        out: MutableList<UiElementSnapshot>,
        path: String,
        resourceIdCounts: Map<String, Int>,
    ) {
        val resourceId = node.viewIdResourceName?.takeIf { it.isNotBlank() }
        // Resource IDs are normally convenient, but Android does not guarantee
        // that a resource ID identifies one node. When an ID is duplicated in
        // the current observation, use the node path so the model can name one
        // exact control and the executor can resolve that same control.
        val stableId = if (resourceId != null && resourceIdCounts[resourceId] == 1) {
            resourceId
        } else {
            "path:$path"
        }
        val bounds = Rect()
        node.getBoundsInScreen(bounds)

        out += UiElementSnapshot(
            id = stableId,
            text = node.text?.toString() ?: "",
            contentDescription = node.contentDescription?.toString() ?: "",
            clickable = node.isClickable,
            enabled = node.isEnabled,
            className = node.className?.toString() ?: "",
            bounds = bounds.toShortString(),
            editable = node.isEditable,
            scrollable = node.isScrollable,
            checkable = node.isCheckable,
            checked = node.isChecked,
            focused = node.isFocused,
            visible = node.isVisibleToUser
        )

        for (i in 0 until node.childCount) {
            node.getChild(i)?.let { child ->
                collect(child, out, "$path.$i", resourceIdCounts)
                child.recycle()
            }
        }
    }
}

data class UiSnapshot(
    val observationId: Long,
    val packageName: String,
    val activity: String,
    val elements: List<UiElementSnapshot>
)

data class UiElementSnapshot(
    val id: String,
    val text: String,
    val contentDescription: String,
    val clickable: Boolean,
    val enabled: Boolean,
    val className: String,
    val bounds: String,
    val editable: Boolean,
    val scrollable: Boolean,
    val checkable: Boolean,
    val checked: Boolean,
    val focused: Boolean,
    val visible: Boolean
)
