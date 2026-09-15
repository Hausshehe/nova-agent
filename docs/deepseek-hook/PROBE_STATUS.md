# Phase G5 status

The probe is intentionally limited to package-load proof. It does not inspect network traffic or credentials and does not hook DeepSeek response internals yet.

Target package: `com.deepseek.chat`

Next device milestone: verify `DEEPSEEK_HOOK_LOADED` in the DeepSeek process log, then add the already-mapped semantic response hook.
