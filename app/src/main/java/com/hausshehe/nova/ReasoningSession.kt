package com.hausshehe.nova

/**
 * Session-scoped reasoning lifecycle.
 *
 * The bootstrap establishes Nova's role and output contract once. Individual
 * reasoning calls then carry only the current task context and fresh Android
 * observation. A session is keyed by the Nova task id, not by a bounded engine
 * cycle, so task retries do not resend the bootstrap.
 */
class ReasoningSession(
    private val provider: ReasoningProvider,
) {
    @Volatile
    private var initialized = false

    private var lastRequestAtMs = 0L

    companion object {
        private const val MIN_REQUEST_GAP_MS = 1000L
        private const val RATE_LIMIT_RETRY_DELAY_MS = 2000L
        private const val RATE_LIMIT_SECOND_RETRY_DELAY_MS = 4000L
        private const val MAX_RATE_LIMIT_RETRIES = 2
    }

    @Synchronized
    fun start() {
        if (initialized) return

        val response = completeWithRateLimitRecovery(
            """
            You are Nova's Android reasoning engine.

            Nova owns the Android device. You do NOT execute actions.
            You receive fresh Android observations and choose exactly ONE next action.

            Rules:
            1. The supplied observation is authoritative.
            2. Never invent UI elements, ids, packages, coordinates, or state.
            3. Use only targets present in the current observation.
            4. Return exactly one action, never an action sequence.
            5. An accepted action does not mean the goal succeeded.
            6. Nova will provide a fresh observation after execution.
            7. Replan from that fresh observation.
            8. If uncertain, do not claim completion.
            9. This bootstrap is initialization only. Do not choose an Android action yet.
            10. Reply to this bootstrap with exactly: BOOTSTRAP_ACK

            Allowed actions:
            tap, type, press_enter, scroll, back, wait, open_uri, open_system, open_app.

            Action rules:
            - tap/type/press_enter/scroll targets must come from the current observation.
            - press_enter is for submitting the currently focused editable field using Android's IME action.
            - open_uri is only for explicit http:// or https:// URIs.
            - open_system requires an exact Android settings action such as
              android.settings.SETTINGS.
            - open_app uses the installed app's human-readable name.
            - Never output shell, adb, Activity Manager commands, coordinates,
              or an action sequence.

            OUTPUT FORMAT:
            - For every action response, return exactly ONE valid JSON object and nothing else.
            - The first character must be { and the last character must be }.
            - Use the "action" field for the action type and "target" for its target when needed.
            - Examples:
              {"action":"open_app","target":"YouTube"}
              {"action":"open_uri","target":"https://example.com"}
              {"action":"open_system","target":"android.settings.SETTINGS"}
              {"action":"tap","target":"<exact observation id>"}
              {"action":"type","target":"<exact observation id>","value":"<text>"}
              {"action":"press_enter","target":"<exact editable observation id>"}
              {"action":"scroll","target":"<exact observation id>","value":"down"}
              {"action":"back"}
              {"action":"wait","value":"1000"}
            - Do NOT use function-call syntax such as open_app({"name":"YouTube"}).
            - Do NOT use natural-language formats such as "open app: YouTube".
            - Do NOT use Markdown, code fences, explanations, labels, or multiple actions.
            - The JSON object must contain only the fields needed for the selected action.
            """.trimIndent(),
        )

        if (response.isBlank()) {
            throw IllegalStateException("DeepSeek bootstrap returned an empty response")
        }

        initialized = true
    }

    fun complete(prompt: String): String {
        start()

        // DeepSeek's native machinery keeps the same conversation for the
        // task. Action generation and semantic verification therefore need an
        // explicit per-turn mode marker so the previous verification response
        // cannot become the model's implicit task for the next turn.
        val trimmed = prompt.trimStart()
        val turnContract = when {
            trimmed.startsWith("CURRENT_CONTEXT:") -> {
                """
                TURN MODE: ACTION_DECISION

                This is an action-generation turn. Ignore any previous
                verification answer as an instruction. Inspect only the CURRENT_CONTEXT
                supplied below and choose exactly ONE next Android action.

                Do not return a verification object. Do not return complete=true/false.
                Return exactly one action JSON object using the bootstrap action schema.
                If the goal is not yet satisfied, choose the single next action.
                If the goal appears satisfied, still do not claim completion here;
                Nova will run a separate verification turn.

                Follow explicit procedural constraints in the goal literally, not
                just the final desired label. If the goal says "scroll", "scroll
                down until", "navigate to", or similar, that required transition
                must actually be performed before treating a visible target as
                the requested result. Do not skip an explicitly required
                intermediate step merely because a similarly named control is
                already visible.

                Distinguish content/feed sections from persistent navigation
                controls. When a goal says to find a section by scrolling, a
                persistent bottom navigation tab with the same label is not the
                section found by scrolling. Do not substitute a navigation tab
                for a content section unless the goal explicitly asks for the
                tab or navigation destination.

                For goals with ordered steps, preserve their order. Do not
                perform a later step before the required earlier transition has
                actually happened. Use recent outcomes together with the current
                observation to determine which required steps have already been
                executed, and replan from the fresh observation after each action.
                """.trimIndent()
            }

            trimmed.startsWith("You are Nova's goal-verification engine.") -> {
                """
                TURN MODE: GOAL_VERIFICATION

                This is a semantic verification turn, not an action-generation turn.
                Do not output an Android action. Evaluate only the verification request
                below and return exactly the requested verification JSON object.
                The next action-generation turn will be explicitly marked separately.
                """.trimIndent()
            }

            else -> {
                "TURN MODE: FOLLOW THE EXPLICIT REQUEST BELOW. Do not infer a different task from earlier turns."
            }
        }

        return completeWithRateLimitRecovery(turnContract + "\n\n" + prompt)
    }

    private fun completeWithRateLimitRecovery(prompt: String): String {
        var attempt = 0
        while (true) {
            paceRequest()
            try {
                val response = provider.complete(prompt)
                lastRequestAtMs = System.currentTimeMillis()
                return response
            } catch (t: Throwable) {
                lastRequestAtMs = System.currentTimeMillis()
                if (!isRateLimit(t)) {
                    throw t
                }

                if (attempt < MAX_RATE_LIMIT_RETRIES) {
                    val delayMs = if (attempt == 0) {
                        RATE_LIMIT_RETRY_DELAY_MS
                    } else {
                        RATE_LIMIT_SECOND_RETRY_DELAY_MS
                    }
                    attempt += 1
                    Thread.sleep(delayMs)
                    continue
                }

                throw RateLimitExhaustedException(t)
            }
        }
    }

    private fun paceRequest() {
        val elapsed = System.currentTimeMillis() - lastRequestAtMs
        val remaining = MIN_REQUEST_GAP_MS - elapsed
        if (remaining > 0L) {
            Thread.sleep(remaining)
        }
    }

    class RateLimitExhaustedException(cause: Throwable) : RuntimeException(
        "DeepSeek rate limit persisted after bounded retries",
        cause,
    )

    private fun isRateLimit(t: Throwable): Boolean {
        var current: Throwable? = t
        while (current != null) {
            val message = current.message?.lowercase() ?: ""
            if (message.contains("too frequent") ||
                message.contains("rate limit") ||
                message.contains("rate-limited") ||
                message.contains("rate limited") ||
                message.contains("throttl") ||
                message.contains("http 429") ||
                message.contains("status 429") ||
                message.contains(" 429")
            ) {
                return true
            }
            current = current.cause
        }
        return false
    }
}

object ReasoningSessionRegistry {
    private val sessions = mutableMapOf<String, ReasoningSession>()

    @Synchronized
    fun session(id: String, provider: ReasoningProvider): ReasoningSession =
        sessions.getOrPut(id) { ReasoningSession(provider) }

    @Synchronized
    fun replace(id: String, provider: ReasoningProvider): ReasoningSession {
        val replacement = ReasoningSession(provider)
        sessions[id] = replacement
        return replacement
    }

    @Synchronized
    fun remove(id: String) {
        sessions.remove(id)
    }
}
