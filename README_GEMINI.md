# Minimal Gemini Agent

A small Python command-line chat client using Google's Gemini API. This is the clean starting point for rebuilding the agent incrementally; the existing Android/Nova code remains untouched.

## Requirements
- Python 3.10+
- A Gemini API key from Google AI Studio

## Run
Set the key in your shell (do not commit it or paste it into source code):

```sh
export GEMINI_API_KEY="your-key"
python -m gemini_agent.main
```

Type a message to chat. Use `/exit` or `/quit` to stop.

The default model is `gemini-2.5-flash`. The client uses only Python's standard library and sends prompts to Gemini's `generateContent` endpoint.

## Current scope
This milestone verifies only the API connection and basic request/response loop. It does not yet control Android, use accessibility, plan actions, or retain conversation history.
