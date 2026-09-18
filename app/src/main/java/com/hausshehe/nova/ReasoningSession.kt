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

    @Synchronized
    fun start() {
        if (initialized) return

        val response = provider.complete(
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
            tap, type, scroll, back, wait, open_uri, open_system, open_app.

            Action rules:
            - tap/type/scroll targets must come from the current observation.
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
        return provider.complete(prompt)
    }
}

object ReasoningSessionRegistry {
    private val sessions = mutableMapOf<String, ReasoningSession>()

    @Synchronized
    fun session(id: String, provider: ReasoningProvider): ReasoningSession =
        sessions.getOrPut(id) { ReasoningSession(provider) }

    @Synchronized
    fun remove(id: String) {
        sessions.remove(id)
    }
}
