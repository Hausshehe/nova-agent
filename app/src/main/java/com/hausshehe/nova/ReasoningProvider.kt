package com.hausshehe.nova

/**
 * Provider-neutral reasoning interface.
 *
 * Nova's agent runtime depends on this contract rather than on a specific
 * model or transport. The native DeepSeek implementation is one provider.
 */
interface ReasoningProvider {
    fun complete(prompt: String): String
}
