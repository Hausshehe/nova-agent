# DeepSeek hook probe

This probe turns the Nova Android app into a legacy Xposed/LSPosed module for the installed DeepSeek app (`com.deepseek.chat`).

Phase G5 intentionally proves only one capability: LSPosed can load Nova code inside the DeepSeek process. It does not inspect credentials, network headers, cookies, or private authentication state.

The next phase can add a narrowly scoped hook for the already identified DeepSeek semantic response fragment methods.
