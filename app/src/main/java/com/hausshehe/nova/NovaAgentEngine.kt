package com.hausshehe.nova

import android.accessibilityservice.AccessibilityService
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.accessibility.AccessibilityNodeInfo
import org.json.JSONArray
import org.json.JSONObject
import java.util.ArrayDeque

data class NovaAgentRunResult(
    val success: Boolean,
    val steps: Int,
    val error: String? = null,
)

data class NovaAgentProgress(
    val steps: Int,
    val status: String,
    val observationId: Long,
    val lastAction: String,
    val lastOutcome: String,
    val error: String? = null,
)

private data class AgentDecision(
    val type: String,
    val targetId: String? = null,
    val value: String? = null,
    val reason: String = "",
)

private data class AgentExecution(
    val accepted: Boolean,
    val changed: Boolean,
    val error: String? = null,
)

private data class GoalVerification(
    val complete: Boolean,
    val evidenceIds: List<String>,
    val reason: String,
)

class NovaAgentEngine(
    private val context: Context,
    private val maxSteps: Int = 24,
    private val client: ReasoningProvider = NativeReasoningClient(),
    private val sessionId: String? = null,
) {
    private val invalidDecisionBudget = 3
    private val recentOutcomes = ArrayDeque<String>()
    private var reasoningSession: ReasoningSession =
        ReasoningSessionRegistry.session(
            sessionId ?: "engine-" + System.identityHashCode(this),
            client,
        )

    fun run(
        goal: String,
        deadlineMs: Long = 0L,
        waitForPackage: String? = null,
        shouldStop: () -> Boolean = { false },
        onProgress: (NovaAgentProgress) -> Unit = {},
    ): NovaAgentRunResult {
        if (goal.isBlank()) return NovaAgentRunResult(false, 0, "goal must not be blank")

        val service = NovaAccessibilityService.instance
            ?: return NovaAgentRunResult(false, 0, "Nova accessibility service is not connected")

        if (!waitForPackage.isNullOrBlank()) {
            val waitDeadline = System.currentTimeMillis() + 2500L
            while (System.currentTimeMillis() < waitDeadline && !shouldStop()) {
                val root = service.rootInActiveWindow
                val activePackage = root?.packageName?.toString()
                root?.recycle()
                if (activePackage == waitForPackage) break
                Thread.sleep(100L)
            }
        }

        try {
            reasoningSession.start()
        } catch (t: Throwable) {
            return NovaAgentRunResult(
                false,
                0,
                "DeepSeek reasoning bootstrap failed: " + (t.message ?: t.javaClass.simpleName),
            )
        }

        observeNow(service)
        var state = ObservationStore.current()
        if (state.elements.isEmpty()) {
            return NovaAgentRunResult(false, 0, "current Android UI observation is empty")
        }

        // DeepSeek owns semantic verification even before the first action.
        // Nova supplies the real current Android observation and enforces the
        // evidence contract; it does not decide what a natural-language goal
        // means from a fixed verb list.
        val initialVerification = verifyGoalWithDeepSeek(
            goal = goal,
            state = state,
            lastAction = "",
            lastOutcome = "initial observation",
        )
        if (initialVerification.complete) {
            onProgress(
                NovaAgentProgress(
                    steps = 0,
                    status = "verified_complete",
                    observationId = state.observationId,
                    lastAction = "",
                    lastOutcome = "DeepSeek verified the current Android state satisfies the goal",
                )
            )
            return NovaAgentRunResult(true, 0)
        }

        var invalidDecisions = 0
        var attempts = 0

        while (attempts < maxSteps) {
            if (shouldStop()) {
                return NovaAgentRunResult(false, attempts, "task cancelled")
            }
            if (deadlineMs > 0L && System.currentTimeMillis() >= deadlineMs) {
                return NovaAgentRunResult(false, attempts, "task deadline reached before verified completion")
            }

            state = ObservationStore.current()
            val raw = try {
                completeReasoning(buildReasoningPrompt(goal, state), goal, state, "action")
            } catch (t: Throwable) {
                return NovaAgentRunResult(
                    false,
                    attempts,
                    "DeepSeek reasoning failed: " + (t.message ?: t.javaClass.simpleName),
                )
            }

            val decision = try {
                parseDecision(raw, state)
            } catch (t: Throwable) {
                invalidDecisions++
                val error = t.message ?: "invalid reasoning decision"
                rememberOutcome("invalid decision: " + error)
                onProgress(
                    NovaAgentProgress(
                        steps = attempts,
                        status = "invalid_decision",
                        observationId = state.observationId,
                        lastAction = "",
                        lastOutcome = error,
                        error = error,
                    )
                )
                if (invalidDecisions > invalidDecisionBudget) {
                    return NovaAgentRunResult(false, attempts, error)
                }
                continue
            }

            invalidDecisions = 0
            attempts++

            val execution = execute(decision, service)
            rememberOutcome(
                "action=" + decision.type +
                    " target=" + decision.targetId.orEmpty() +
                    " accepted=" + execution.accepted +
                    " changed=" + execution.changed +
                    " error=" + execution.error.orEmpty()
            )
            onProgress(
                NovaAgentProgress(
                    steps = attempts,
                    status = if (execution.accepted) "executed" else "rejected",
                    observationId = state.observationId,
                    lastAction = actionSummary(decision),
                    lastOutcome = executionSummary(execution),
                    error = execution.error,
                )
            )

            val after = when {
                decision.type == "wait" -> {
                    observeNow(service)
                    ObservationStore.current()
                }
                execution.accepted -> waitForFreshObservation(state, service, deadlineMs)
                else -> {
                    observeNow(service)
                    ObservationStore.current()
                }
            }

            // DeepSeek owns semantic goal verification. Nova still enforces the
            // mechanical safety contract for actions and evidence IDs, but it must
            // not decide that a human goal is complete from hard-coded goal syntax.
            // This is especially important for compound goals such as
            // "Open YouTube and then tap Search".
            val verification = verifyGoalWithDeepSeek(
                goal = goal,
                state = after,
                lastAction = actionSummary(decision),
                lastOutcome = executionSummary(execution),
            )

            if (verification.complete) {
                onProgress(
                    NovaAgentProgress(
                        steps = attempts,
                        status = "verified_complete",
                        observationId = after.observationId,
                        lastAction = actionSummary(decision),
                        lastOutcome = "goal verified from fresh Android state",
                    )
                )
                return NovaAgentRunResult(true, attempts)
            }
        }

        return NovaAgentRunResult(
            false,
            attempts,
            "step budget exhausted before verified completion",
        )
    }

    private fun buildReasoningPrompt(goal: String, state: UiSnapshot): String {
        val root = JSONObject().apply {
            put("goal", goal)
            put("current_state", statePayload(state))
            val outcomes = JSONArray()
            recentOutcomes.forEach { outcomes.put(it) }
            put("recent_outcomes", outcomes)
        }

        return """
            CURRENT_CONTEXT:
        """.trimIndent() + "\n" + root.toString()
    }

    private fun completeReasoning(prompt: String, goal: String, state: UiSnapshot, mode: String): String {
        return try {
            reasoningSession.complete(prompt)
        } catch (t: ReasoningSession.RateLimitExhaustedException) {
            val id = sessionId ?: "engine-" + System.identityHashCode(this)
            reasoningSession = ReasoningSessionRegistry.replace(id, client)
            reasoningSession.complete(
                buildRateLimitHandoffPrompt(goal, state, mode, prompt)
            )
        }
    }

    private fun buildRateLimitHandoffPrompt(
        goal: String,
        state: UiSnapshot,
        mode: String,
        originalPrompt: String,
    ): String =
        """
        NEW REASONING SESSION HANDOFF

        The previous Nova reasoning session was temporarily rate limited.
        Continue the same task from the current Android state below.

        GOAL:
        $goal

        CURRENT MODE:
        $mode

        IMPORTANT:
        - Treat the current Android observation as authoritative.
        - Do not assume any action succeeded unless the current observation supports it.
        - Preserve the goal's explicit procedural and ordered steps.
        - Continue from the current state; do not restart completed work without evidence.
        - Return exactly the output required by the task below.

        ORIGINAL REQUEST:
        $originalPrompt
        """.trimIndent()

    private fun verifyGoalWithDeepSeek(
        goal: String,
        state: UiSnapshot,
        lastAction: String,
        lastOutcome: String,
    ): GoalVerification {
        return try {
            parseVerification(
                completeReasoning(
                    buildVerificationPrompt(
                        goal = goal,
                        state = state,
                        lastAction = lastAction,
                        lastOutcome = lastOutcome,
                    ),
                    goal,
                    state,
                    "verification",
                ),
                state,
            )
        } catch (t: Throwable) {
            GoalVerification(
                complete = false,
                evidenceIds = emptyList(),
                reason = "DeepSeek verification failed: " + (t.message ?: t.javaClass.simpleName),
            )
        }
    }

    private fun buildVerificationPrompt(
        goal: String,
        state: UiSnapshot,
        lastAction: String,
        lastOutcome: String,
    ): String {
        return buildString {
            append(
                """
                You are Nova's goal-verification engine.

                Decide whether the user goal is ALREADY satisfied by the CURRENT
                Android observation. Do not suggest another action. Do not rely on
                memory of previous screens except for the task goal itself.

                You are the semantic authority for completion. Interpret the goal
                as a human instruction, including compound or sequential goals.
                Judge the requested OUTCOME, not whether Nova merely executed an
                action. For compound or sequential goals, every required step must
                be reflected in the current state or in concrete outcome evidence.
                The mere presence of a control that was supposed to be tapped is
                NOT evidence that the tap happened. For example, if the goal says
                "Open YouTube and then tap Search", a YouTube home screen that still
                shows a Search button is NOT complete. A resulting YouTube search
                screen, such as a visible search input or search-page UI, is evidence
                that the Search action actually took effect.

                The LAST_ACTION and LAST_OUTCOME are supporting execution evidence,
                not permission to infer a state that is absent from CURRENT_STATE.
                In particular, do not treat "accepted=true changed=true" as proof
                that an action achieved its intended semantic outcome when the
                current observation still shows the pre-action UI.

                Return complete=true only when the visible current state provides
                concrete evidence that the requested outcome is satisfied. If there
                is meaningful uncertainty, return complete=false.

                Evidence must reference only element ids present in the current
                observation. Never invent ids. A completion decision with no valid
                visible evidence ids is invalid.

                Return JSON only:
                {
                  "complete": true | false,
                  "evidence_ids": ["current element id", "..."],
                  "reason": "brief explanation"
                }

                GOAL:
                """.trimIndent()
            )
            append("\n")
            append(goal)
            append("\n\nLAST_ACTION:\n")
            append(lastAction)
            append("\n\nLAST_OUTCOME:\n")
            append(lastOutcome)
            append("\n\nCURRENT_STATE:\n")
            append(statePayload(state).toString())
        }
    }
    private fun parseVerification(
        raw: String,
        state: UiSnapshot,
    ): GoalVerification {
        val json = extractObject(raw)
        val complete = json.optBoolean("complete", false)
        val evidence = json.optJSONArray("evidence_ids")
        val ids = mutableListOf<String>()

        if (evidence != null) {
            for (index in 0 until evidence.length()) {
                val id = evidence.optString(index, "").trim()
                if (id.isNotBlank() && state.elements.any { it.id == id && it.visible }) {
                    ids.add(id)
                }
            }
        }

        if (complete && ids.isEmpty()) {
            return GoalVerification(
                false,
                emptyList(),
                "completion claim lacked valid visible evidence",
            )
        }

        return GoalVerification(
            complete = complete,
            evidenceIds = ids,
            reason = json.optString("reason", "").take(240),
        )
    }
    private fun statePayload(state: UiSnapshot): JSONObject {
        val root = JSONObject().apply {
            put("package", state.packageName)
            put("activity", state.activity)
            put("observation_id", state.observationId)
        }

        val elements = JSONArray()
        var count = 0
        for (element in state.elements) {
            if (!element.visible || count >= 80) continue

            val label = listOf(element.text, element.contentDescription)
                .filter { it.isNotBlank() }
                .joinToString(" ")
                .trim()

            if (label.isBlank() &&
                !element.clickable &&
                !element.editable &&
                !element.scrollable
            ) continue

            elements.put(JSONObject().apply {
                put("id", element.id)
                put("label", label)
                put("clickable", element.clickable)
                put("editable", element.editable)
                put("scrollable", element.scrollable)
                put("checkable", element.checkable)
                put("checked", element.checked)
                put("enabled", element.enabled)
                put("focused", element.focused)
            })
            count++
        }

        root.put("elements", elements)
        return root
    }

    private fun jsonNullableString(json: JSONObject, key: String): String? {
        if (!json.has(key) || json.isNull(key)) return null
        return json.optString(key, "").trim().ifBlank { null }
    }

    private fun parseDecision(raw: String, state: UiSnapshot): AgentDecision {
        val normalized = raw.trim()

        // DeepSeek can return a tool-call-shaped action such as
        // open_app({"name":"YouTube"}) even when the bootstrap asks for JSON.
        // Accept that equivalent wire form as well as the documented JSON form.
        // The executor still receives the same normalized AgentDecision.
        val functionMatch = Regex(
            """^([A-Za-z_][A-Za-z0-9_]*)\\s*\\((.*)\\)\\s*$""",
            setOf(RegexOption.DOT_MATCHES_ALL),
        ).matchEntire(normalized)

        val functionType = functionMatch?.groupValues?.get(1)?.lowercase()
        val json = if (functionMatch != null) {
            val arguments = functionMatch.groupValues[2].trim()
            if (arguments.isBlank()) JSONObject() else extractObject(arguments)
        } else {
            extractObject(raw)
        }

        // The reasoning bootstrap defines the public wire schema as:
        // {"action":"...", "target":"...", ...}
        // Older Nova code expected internal field names action_type/target_id.
        // Accept both forms and normalize them here so the model contract and
        // executor contract cannot drift apart again.
        val type = (
            jsonNullableString(json, "action_type")
                ?: jsonNullableString(json, "action")
                ?: functionType
                ?: ""
            ).lowercase()

        val targetId = jsonNullableString(json, "target_id")
            ?: jsonNullableString(json, "target")

        val reason = json.optString("reason", "model decision").take(240)
        val value = jsonNullableString(json, "value")
        val namedTarget = jsonNullableString(json, "name")
        val uri = jsonNullableString(json, "uri")

        fun actionValue(): String? = value ?: targetId ?: namedTarget ?: uri

        when (type) {
            "tap", "click" -> {
                require(targetId != null) { "tap requires target" }
                val target = state.elements.firstOrNull { it.id == targetId }
                    ?: throw IllegalArgumentException("tap target is not present in current observation")
                require(target.visible && target.enabled && target.clickable) {
                    "tap target is not visible, enabled, and clickable"
                }
                // Some model/tool-call serializers attach the visible label as
                // optional tap metadata. The observation ID remains authoritative,
                // so accept it when it matches the selected node rather than
                // rejecting an otherwise valid action.
                if (value != null) {
                    val label = (target.text + " " + target.contentDescription).trim()
                    require(value == label || value in listOf(target.text, target.contentDescription).filter { it.isNotBlank() }) {
                        "tap value does not match target label"
                    }
                }
            }

            "type", "input_text" -> {
                require(targetId != null) { "type requires target" }
                require(!value.isNullOrEmpty()) { "type requires value" }
                val target = state.elements.firstOrNull { it.id == targetId }
                    ?: throw IllegalArgumentException("type target is not present in current observation")
                require(target.visible && target.enabled && target.editable) {
                    "type target is not visible, enabled, and editable"
                }
            }

            "press_enter" -> {
                require(targetId != null) { "press_enter requires target" }
                val target = state.elements.firstOrNull { it.id == targetId }
                    ?: throw IllegalArgumentException("press_enter target is not present in current observation")
                require(target.visible && target.enabled && target.editable) {
                    "press_enter target is not visible, enabled, and editable"
                }
            }

            "scroll" -> {
                if (targetId != null) {
                    val target = state.elements.firstOrNull { it.id == targetId }
                        ?: throw IllegalArgumentException("scroll target is not present in current observation")
                    require(target.visible && target.enabled && target.scrollable) {
                        "scroll target is not visible, enabled, and scrollable"
                    }
                }
                if (value != null) {
                    require(value.lowercase() in setOf("up", "down", "forward", "backward")) {
                        "scroll value must be up, down, forward, or backward"
                    }
                }
            }

            "back" -> require(targetId == null && value == null) {
                "back cannot carry target or value"
            }

            "wait" -> {
                require(targetId == null) { "wait cannot carry target" }
                val waitMs = (value ?: "1000").toLongOrNull()
                    ?: throw IllegalArgumentException("wait value must be milliseconds")
                require(waitMs in 250L..120000L) {
                    "wait must be between 250 and 120000 ms"
                }
            }

            "open_uri" -> {
                require(targetId == null || value == null) {
                    "open_uri cannot carry both target and value"
                }
                val uri = actionValue()
                require(!uri.isNullOrBlank()) { "open_uri requires a URI" }
                require(
                    uri.startsWith("https://", true) || uri.startsWith("http://", true)
                ) { "open_uri requires an http(s) URI" }
            }

            "open_app" -> {
                require(targetId == null || value == null) {
                    "open_app cannot carry both target and value"
                }
                require(!actionValue().isNullOrBlank()) { "open_app requires an app name" }
            }

            "open_system" -> {
                require(targetId == null || value == null) {
                    "open_system cannot carry both target and value"
                }
                val systemAction = actionValue()
                require(!systemAction.isNullOrBlank()) {
                    "open_system requires an Android system action"
                }
                require(systemAction.startsWith("android.settings.", true)) {
                    "open_system requires an android.settings.* action"
                }
            }

            else -> throw IllegalArgumentException("unsupported action: " + type)
        }

        return AgentDecision(
            type = type,
            targetId = when (type) {
                "open_app", "open_uri", "open_system" -> null
                else -> targetId
            },
            value = when (type) {
                "open_app", "open_uri", "open_system" -> actionValue()
                else -> value
            },
            reason = reason,
        )
    }

    private fun execute(
        decision: AgentDecision,
        service: NovaAccessibilityService,
    ): AgentExecution {
        return try {
            when (decision.type) {
                "tap", "click" -> executeTap(service, decision.targetId!!)
                "type", "input_text" -> executeType(service, decision.targetId!!, decision.value!!)
                "press_enter" -> executePressEnter(service, decision.targetId!!)
                "scroll" -> executeScroll(service, decision.targetId, decision.value)
                "back" -> AgentExecution(
                    accepted = service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK),
                    changed = true,
                )
                "wait" -> {
                    Thread.sleep(decision.value!!.toLong())
                    AgentExecution(true, false)
                }
                "open_uri" -> {
                    val intent = Intent(Intent.ACTION_VIEW, Uri.parse(decision.value!!)).apply {
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    }
                    context.startActivity(intent)
                    AgentExecution(true, true)
                }
                "open_app" -> executeOpenApp(decision.value!!)
                "open_system" -> {
                    val intent = Intent(decision.value!!).apply {
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    }
                    context.startActivity(intent)
                    AgentExecution(true, true)
                }
                else -> AgentExecution(false, false, "unsupported action: " + decision.type)
            }
        } catch (t: Throwable) {
            AgentExecution(false, false, t.message ?: t.javaClass.simpleName)
        }
    }

    private fun executeOpenApp(appName: String): AgentExecution {
        val wanted = tokenize(appName)
        if (wanted.isEmpty()) return AgentExecution(false, false, "app name is empty")

        // Resolve the same launcher surface Android exposes to the user. This is
        // more reliable than getLaunchIntentForPackage() on devices where an app
        // has a launcher activity but its package-level launch intent is absent or
        // behaves differently for the current task.
        val launcherIntent = Intent(Intent.ACTION_MAIN).apply {
            addCategory(Intent.CATEGORY_LAUNCHER)
        }
        val launcherActivities = context.packageManager
            .queryIntentActivities(launcherIntent, 0)
            .asSequence()
            .filter { it.activityInfo.packageName != context.packageName }
            .map { info ->
                val label = info.loadLabel(context.packageManager).toString()
                Triple(info.activityInfo.packageName, info.activityInfo.name, label)
            }
            .distinctBy { it.first }
            .filter { (_, _, label) ->
                val tokens = tokenize(label)
                wanted.all { it in tokens }
            }
            .toList()

        if (launcherActivities.size != 1) {
            return AgentExecution(
                false,
                false,
                if (launcherActivities.isEmpty()) {
                    "installed launcher app not found: " + appName
                } else {
                    "app name is ambiguous: " + appName
                },
            )
        }

        val (packageName, activityName, _) = launcherActivities.single()
        val intent = Intent(Intent.ACTION_MAIN).apply {
            addCategory(Intent.CATEGORY_LAUNCHER)
            setClassName(packageName, activityName)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }

        return try {
            context.startActivity(intent)
            AgentExecution(true, true)
        } catch (t: Throwable) {
            AgentExecution(
                false,
                false,
                "failed to launch " + appName + ": " + (t.message ?: t.javaClass.simpleName),
            )
        }
    }

    private fun executeTap(
        service: NovaAccessibilityService,
        targetId: String,
    ): AgentExecution {
        val root = service.rootInActiveWindow
            ?: return AgentExecution(false, false, "no active accessibility window")
        try {
            val node = findNode(root, targetId, "0")
                ?: return AgentExecution(false, false, "tap target disappeared before execution")
            return try {
                if (!node.isVisibleToUser || !node.isEnabled || !node.isClickable) {
                    AgentExecution(false, false, "tap target is no longer actionable")
                } else {
                    AgentExecution(
                        accepted = node.performAction(AccessibilityNodeInfo.ACTION_CLICK),
                        changed = false,
                    )
                }
            } finally {
                if (node !== root) node.recycle()
            }
        } finally {
            root.recycle()
        }
    }

    private fun executeType(
        service: NovaAccessibilityService,
        targetId: String,
        text: String,
    ): AgentExecution {
        val root = service.rootInActiveWindow
            ?: return AgentExecution(false, false, "no active accessibility window")
        try {
            val node = findNode(root, targetId, "0")
                ?: return AgentExecution(false, false, "type target disappeared before execution")
            return try {
                if (!node.isVisibleToUser || !node.isEnabled || !node.isEditable) {
                    AgentExecution(false, false, "type target is no longer editable")
                } else {
                    node.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
                    val args = Bundle().apply {
                        putCharSequence(
                            AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,
                            text,
                        )
                    }
                    AgentExecution(
                        accepted = node.performAction(
                            AccessibilityNodeInfo.ACTION_SET_TEXT,
                            args,
                        ),
                        changed = false,
                    )
                }
            } finally {
                if (node !== root) node.recycle()
            }
        } finally {
            root.recycle()
        }
    }

    private fun executePressEnter(
        service: NovaAccessibilityService,
        targetId: String,
    ): AgentExecution {
        if (android.os.Build.VERSION.SDK_INT < android.os.Build.VERSION_CODES.R) {
            return AgentExecution(false, false, "press_enter requires Android 11 or newer")
        }

        val root = service.rootInActiveWindow
            ?: return AgentExecution(false, false, "no active accessibility window")
        try {
            val node = findNode(root, targetId, "0")
                ?: return AgentExecution(false, false, "press_enter target disappeared before execution")
            return try {
                if (!node.isVisibleToUser || !node.isEnabled || !node.isEditable) {
                    AgentExecution(false, false, "press_enter target is no longer editable")
                } else {
                    if (!node.isFocused) {
                        node.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
                    }
                    val supportsImeEnter = node.actionList.any {
                        it.id == AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.id
                    }
                    if (!supportsImeEnter) {
                        AgentExecution(false, false, "target does not expose an IME enter action")
                    } else {
                        AgentExecution(
                            accepted = node.performAction(
                                AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.id
                            ),
                            changed = false,
                        )
                    }
                }
            } finally {
                if (node !== root) node.recycle()
            }
        } finally {
            root.recycle()
        }
    }

    private fun executeScroll(
        service: NovaAccessibilityService,
        targetId: String?,
        direction: String?,
    ): AgentExecution {
        val root = service.rootInActiveWindow
            ?: return AgentExecution(false, false, "no active accessibility window")
        try {
            val node = if (targetId == null) root else findNode(root, targetId, "0")
            if (node == null) {
                return AgentExecution(false, false, "scroll target disappeared before execution")
            }

            return try {
                if (!node.isVisibleToUser || !node.isEnabled) {
                    AgentExecution(false, false, "scroll target is no longer available")
                } else if (targetId != null && !node.isScrollable) {
                    AgentExecution(false, false, "scroll target is no longer scrollable")
                } else {
                    val action = when (direction?.lowercase()) {
                        "up", "backward" -> AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
                        else -> AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
                    }
                    AgentExecution(
                        accepted = node.performAction(action),
                        changed = false,
                    )
                }
            } finally {
                if (node !== root) node.recycle()
            }
        } finally {
            root.recycle()
        }
    }

    private fun observeNow(service: NovaAccessibilityService) {
        service.rootInActiveWindow?.let { root ->
            try {
                ObservationStore.update(root)
            } finally {
                root.recycle()
            }
        }
    }

    private fun waitForFreshObservation(
        before: UiSnapshot,
        service: NovaAccessibilityService,
        deadlineMs: Long,
    ): UiSnapshot {
        val maxWait = 5000L
        val deadline = minOf(
            System.currentTimeMillis() + maxWait,
            if (deadlineMs > 0L) deadlineMs else Long.MAX_VALUE,
        )

        while (System.currentTimeMillis() < deadline) {
            val current = ObservationStore.current()
            if (!sameUi(before, current)) return current
            Thread.sleep(100L)
        }

        observeNow(service)
        return ObservationStore.current()
    }

    private fun sameUi(before: UiSnapshot, after: UiSnapshot): Boolean =
        before.packageName == after.packageName &&
            before.activity == after.activity &&
            before.elements == after.elements

    private fun isGoalComplete(
        goal: String,
        after: UiSnapshot,
        before: UiSnapshot? = null,
    ): Boolean {
        val words = tokenize(goal).toMutableList()
        val deadlineWord = words.indexOf("by")
        if (deadlineWord >= 0) {
            words.subList(deadlineWord, words.size).clear()
        }
        if (words.isEmpty()) return false

        val verb = words.first()
        if (verb in ACTION_VERBS) {
            return before != null && after != before
        }

        val targetWords = if (
            verb in COMPLETION_MARKERS || words.drop(1).any { it in COMPLETION_MARKERS }
        ) {
            words.filter {
                it !in STOP_WORDS &&
                    it !in COMPLETION_MARKERS &&
                    it !in setOf("up", "off", "down")
            }
        } else {
            words.drop(1).filter {
                it !in STOP_WORDS && it !in setOf("up", "off", "down")
            }
        }.toSet()

        if (targetWords.isEmpty()) return false

        if (verb in CHECK_ON_VERBS || verb in CHECK_OFF_VERBS) {
            val expected = verb in CHECK_ON_VERBS
            return after.elements.any { element ->
                element.visible &&
                    element.checkable &&
                    element.checked == expected &&
                    targetWords.all {
                        it in tokenize(element.text + " " + element.contentDescription)
                    }
            }
        }

        val visibleElements = after.elements.filter { it.visible }
        val visibleTokens = visibleElements
            .flatMap { tokenize(it.text + " " + it.contentDescription) }
            .toSet()

        if (verb in STATE_VERBS) {
            if (!targetWords.all { it in visibleTokens }) return false

            // For "open/show/navigate to X", current application identity is
            // stronger evidence than arbitrary text. This is what prevents
            // terminal history, notifications, or hidden content from satisfying
            // an app/screen goal accidentally.
            val packageMatchesTarget = currentAppMatchesTarget(targetWords, after)

            if (before == null) {
                return packageMatchesTarget || strongVisibleTargetEvidence(targetWords, after)
            }

            val wasAlreadyVisible = before.elements.any { element ->
                element.visible &&
                    targetWords.all {
                        it in tokenize(element.text + " " + element.contentDescription)
                    }
            }

            // A package/activity change only proves that navigation happened.
            // It does NOT prove that the requested destination was reached.
            // Require destination-specific evidence instead.
            return packageMatchesTarget ||
                (!wasAlreadyVisible && strongVisibleTargetEvidence(targetWords, after))
        }

        val explicitCompletion =
            verb in COMPLETION_MARKERS ||
                words.drop(1).any { it in COMPLETION_MARKERS }

        if (explicitCompletion) {
            val hasTarget = targetWords.all { it in visibleTokens }
            val hasCompletion = visibleElements.any { element ->
                !element.clickable &&
                    tokenize(element.text + " " + element.contentDescription)
                        .any { it in COMPLETION_MARKERS }
            }
            return hasTarget && hasCompletion
        }

        return false
    }

    private fun tokenize(text: String): Set<String> =
        Regex("[A-Za-z0-9]+").findAll(text.lowercase()).map { it.value }.toSet()

    private fun currentAppMatchesTarget(
        targetWords: Set<String>,
        state: UiSnapshot,
    ): Boolean {
        if (targetWords.isEmpty() || state.packageName.isBlank()) return false

        val packageTokens = tokenize(state.packageName)
        val label = try {
            val info = context.packageManager.getApplicationInfo(state.packageName, 0)
            context.packageManager.getApplicationLabel(info).toString()
        } catch (_: Throwable) {
            ""
        }

        val appTokens = packageTokens + tokenize(label)
        return targetWords.all { it in appTokens }
    }

    private fun strongVisibleTargetEvidence(
        targetWords: Set<String>,
        state: UiSnapshot,
    ): Boolean {
        return state.elements.any { element ->
            if (!element.visible) return@any false
            val text = element.text + " " + element.contentDescription
            val tokens = tokenize(text)
            targetWords.all { it in tokens } &&
                (element.className.contains("TextView", true) ||
                    element.className.contains("Button", true) ||
                    element.className.contains("Toolbar", true) ||
                    element.className.contains("EditText", true))
        }
    }


    private fun extractObject(text: String): JSONObject {
        val start = text.indexOf('{')
        require(start >= 0) { "reasoner response contains no JSON object" }

        var depth = 0
        var quoted = false
        var escaped = false

        for (index in start until text.length) {
            val ch = text[index]
            if (quoted) {
                when {
                    escaped -> escaped = false
                    ch == '\\' -> escaped = true
                    ch == '"' -> quoted = false
                }
                continue
            }

            when (ch) {
                '"' -> quoted = true
                '{' -> depth++
                '}' -> {
                    depth--
                    if (depth == 0) {
                        return JSONObject(text.substring(start, index + 1))
                    }
                }
            }
        }

        throw IllegalArgumentException("reasoner response contains incomplete JSON")
    }

    private fun rememberOutcome(value: String) {
        recentOutcomes.addLast(value.take(320))
        while (recentOutcomes.size > 6) recentOutcomes.removeFirst()
    }

    private fun actionSummary(decision: AgentDecision): String =
        decision.type +
            decision.targetId?.let { " target=" + it }.orEmpty() +
            if (decision.type == "type") {
                " value-length=" + (decision.value?.length ?: 0)
            } else {
                ""
            } +
            decision.reason.takeIf { it.isNotBlank() }?.let { " reason=" + it }.orEmpty()

    private fun executionSummary(execution: AgentExecution): String =
        "accepted=" + execution.accepted +
            " changed=" + execution.changed +
            execution.error?.let { " error=" + it }.orEmpty()

    private fun findNode(
        node: AccessibilityNodeInfo,
        targetId: String,
        path: String,
    ): AccessibilityNodeInfo? {
        if (node.viewIdResourceName == targetId || "path:" + path == targetId) return node

        for (index in 0 until node.childCount) {
            val child = node.getChild(index) ?: continue
            val result = findNode(child, targetId, path + "." + index)
            if (result != null) {
                if (result !== child) child.recycle()
                return result
            }
            child.recycle()
        }
        return null
    }

    private companion object {
        val ACTION_VERBS = setOf("tap", "click", "type", "scroll", "swipe", "back", "wait")
        val COMPLETION_MARKERS = setOf("complete", "completed", "completion", "finished", "finish", "done")
        val STATE_VERBS = setOf("open", "show", "display", "navigate", "go", "select", "choose")
        val CHECK_ON_VERBS = setOf("enable", "turn", "check", "activate")
        val CHECK_OFF_VERBS = setOf("disable", "uncheck", "deactivate")
        val STOP_WORDS = setOf(
            "a", "an", "the", "to", "into", "on", "in", "at", "for", "and",
            "please", "then", "screen", "page",
        )
    }
}
