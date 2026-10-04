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

## Memory
Conversation history is saved locally in `memory.json` and loaded the next time the agent starts. The file is ignored by Git because it may contain private conversation data. The agent keeps the most recent 40 messages (about 20 exchanges) to limit request size. This is conversation-history persistence, not yet a separate system for extracting and managing durable facts.

## Tests
Run offline tests with:

```sh
python -m unittest discover -s tests -v
```

The client uses Python's standard library and sends prompts to Gemini's `generateContent` endpoint. It does not yet control Android or plan actions.
