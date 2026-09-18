# Nova Agent → Claude Handoff

## Mission

Continue Nova as an **adaptive Android assistant agent** with two user-facing modes:

1. **Instant assistant:** the user invokes Nova from anywhere on Android (eventually by holding the Home/assistant button), asks a natural-language request, and Nova completes it across apps.
2. **Long-running agent:** the user can say something like "Nova, finish this by 8 AM", then leave. Nova persists the goal, works toward it, recovers/replans as needed, resumes after interruptions, and reports completion.

The intended product is not a chatbot with a few Android commands. Nova owns the task lifecycle and reasons from current Android reality.

## Current branch / checkpoint

Working branch:

`phase-g11-session-bootstrap-trace`

Latest critical commits:

- `2509a753b6fa5ea05f1aafa85032037be699a6dd` — `Bootstrap DeepSeek automatically for native prompts`
- `150fe74431a8438368099bc7576dbba0a0ee1789` — `Wait for DeepSeek native session readiness`

The second commit fixed the cold-start race: the native socket could listen before the DeepSeek `np1` session was ready.

## Current verified result

The user pulled, built, and installed the latest code on the rooted TECNO KJ5.

Real-device cold-start test:

```bash
am force-stop com.deepseek.chat
printf '%s\n' '{"command":"deepseek_native_prompt","prompt":"Reply with exactly COLD_NATIVE_OK"}' | nc 127.0.0.1 18765
```

Returned:

```json
{"ok":true,"accepted":true,"completed":true,"text":"COLD_NATIVE_OK"}
```

This is the key milestone.

It proves:

- DeepSeek can be completely stopped.
- Nova can trigger DeepSeek bootstrap itself.
- DeepSeek's injected hook loads.
- DeepSeek's native session is created.
- Nova obtains the live `np1`.
- Nova can invoke DeepSeek's native completion machinery without a manually typed UI message.
- The native network/backend path works.
- Native response events return to Nova.
- The complete round trip works from a cold start.

There is a small visible DeepSeek flash during cold start. It is currently accepted as a cosmetic Android task/window behavior. Do not spend the next phase trying to remove it unless it becomes a real product blocker.

## Exact DeepSeek/Nova connection

### Nova side

`BridgeServer.kt` listens on:

`127.0.0.1:18765`

Relevant command:

`deepseek_native_prompt`

The current flow is:

1. Validate the prompt.
2. Mark the Nova-side response collector active.
3. Try localhost `127.0.0.1:18766`.
4. If the native bridge is unavailable, launch:
   `com.deepseek.chat.MainActivity`.
5. Poll for the native bridge for up to 5 seconds.
6. Send the original JSON request to port 18766.
7. Wait for native response events for up to 30 seconds.
8. Return the completed response text.

Important: an open port is not treated as session readiness. The in-process hook itself waits up to 5 seconds for `liveNp1`.

### DeepSeek process side

`DeepSeekNativeInvokeProbe.java` is loaded into `com.deepseek.chat` through the existing legacy/Xposed-compatible injection mechanism.

It hooks:

`com.deepseek.chat.App.onCreate`

for lifecycle diagnostics.

It hooks:

`com.deepseek.chat.MainActivity`

and framework `Activity.onCreate/onStart` to capture/hide the bootstrap Activity.

The actual native session hook is:

`x05.K0(...)`

After `K0` returns:

```text
K0 result
  ↓
kk1
  ↓
kk1.d.getValue()
  ↓
zj1
  ↓
zj1.c
  ↓
np1
```

The hook stores that `np1` as `liveNp1`.

The native control server listens on:

`127.0.0.1:18766`

When Nova sends a prompt, the hook:

```text
live np1
  ↓
np1.Q()
  ↓
be1.l()
  ↓
lr1.a
  ↓
it8.k()
  ↓
native n1
  ↓
np1.U(np1, prompt, n1, null, false, 0x4c)
```

This enters DeepSeek's own higher-level native send/completion machinery.

Do not replace this with a direct HTTP implementation. The whole point of this milestone is that DeepSeek owns its own session/network/completion behavior.

### Response path

DeepSeek's native stream produces events through its own internals.

Existing hooks observe:

- `x21` stream events
- `n63` response/semantic fragments
- other request/response diagnostics

Nova's `deepseek_event` command feeds these events into `BridgeServer`'s response collector.

The bridge returns the accumulated text only after the native response reaches the finished state.

## Why the cold-start race happened

Initial implementation assumed:

```text
port 18766 listening = native session ready
```

That was false.

DeepSeek's process could start the control server before `x05.K0` had produced the live `np1`.

The first cold-start test therefore returned:

```text
DeepSeek native session object is not ready
```

Fix:

```text
BridgeServer
  ↓
connect to 18766
  ↓
DeepSeek hook receives request
  ↓
await liveNp1
  ↓
poll actual session readiness (100 ms)
  ↓
invoke U only after np1 exists
```

This is now verified on the real phone.

## Cold-start UI behavior

The bootstrap launches DeepSeek's explicit:

`com.deepseek.chat.MainActivity`

The hook sets the Activity decor view alpha to zero in `onCreate` and `onStart`, then moves the task back after native session resolution.

Android can still briefly surface the task before the Activity hook gets full control. Testing showed a very short visual flash.

This is accepted.

Once DeepSeek is running and its native session is alive, later prompts use the existing native session and do not intentionally launch the UI again.

If Android kills the DeepSeek process, the next native prompt may need another bootstrap.

The user's foreground app is not intentionally restarted or navigated. The bootstrap task is moved back after session initialization.

## Safety / boundary rules

Preserve these project boundaries:

- No credential extraction.
- No token/cookie extraction.
- No replay of authenticated DeepSeek requests.
- No auth bypass.
- No PoW bypass.
- No standalone HTTP client pretending to be the DeepSeek app.
- Use DeepSeek's own in-process native machinery.
- Keep Android actions under Nova's controlled capability boundary.

## Product architecture

Nova should eventually look like:

```text
                       USER
                        ↓
               Nova Assistant UI
               / Home invocation
                        ↓
                 Nova Task Runtime
                        ↓
               Current Android State
                 /             \
        Accessibility          Screenshot
             |                    |
             |               Gemini Vision
             |                    |
             └─────────┬──────────┘
                       ↓
                DeepSeek Reasoner
                       ↓
             Structured next decision
                       ↓
                Nova Action Resolver
                       ↓
                Android capability
                       ↓
                  Fresh observe
                       ↓
             Verify goal / transition
                  /           \
              success        mismatch
                 |               |
                done          replan
                                 ↓
                             DeepSeek
```

### Division of responsibility

**Nova**

- task lifecycle
- goal state
- observation orchestration
- action capability
- current-state target resolution
- verification
- recovery
- replanning loop
- persistence
- deadlines
- background/resume behavior
- user-facing assistant surface
- eventual Android assistant role

**DeepSeek**

- general reasoning
- interpreting structured current state
- planning the next useful step
- diagnosing unexpected states
- deciding when replanning is needed
- reasoning about the user's goal

**Gemini Vision**

- screenshot understanding
- visual target identification
- cases where accessibility is incomplete or ambiguous
- visual confirmation

Gemini is not intended to replace DeepSeek as the general brain.

## Adaptability requirement

Do not regress into hard-coded UI sequences.

Nova must not depend on:

- fixed coordinates
- "tap X, then tap Y" scripts
- assumptions that a button remains in one location
- one fixed UI layout
- blindly replaying an old successful sequence

Instead:

```text
observe current reality
        ↓
reason
        ↓
resolve action against CURRENT state
        ↓
act
        ↓
observe again
        ↓
verify
        ↓
replan if reality differs
```

An Android/app UI change is expected input to the adaptive loop, not a reason for the agent to fail.

## Long-running agent requirement

The user wants:

> "Nova, finish this by 8 AM."

This requires a persistent task system, not a long-running foreground process.

Persist at least:

- task/goal
- deadline
- task status
- current subgoal
- evidence of last verified state
- last action
- result of last action
- failure/recovery information
- next intended objective
- timestamps

Nova should be able to:

1. accept a deadline-aware goal;
2. plan work;
3. execute when the device permits;
4. persist progress;
5. pause/wait;
6. resume after process death/restart;
7. re-observe before continuing;
8. replan when reality changed;
9. stop when the goal is verified complete;
10. notify the user.

Do not model the deadline as merely a reminder/alarm.

## Home-button assistant requirement

End goal:

```text
User holds Home / invokes Android assistant
          ↓
Nova appears
          ↓
User speaks/types naturally
          ↓
same Nova task runtime
```

The invocation mechanism should remain separate from the agent runtime.

Do this after the agent is reliable enough that Nova has something worth invoking. Later investigate Android's assistant-role/default-assistant integration and what is possible on the user's rooted TECNO Android 13 device.

## Current implementation order

Recommended sequence from here:

### 1. Reasoning boundary

Locate the existing Nova task/reasoning abstraction and make DeepSeek Native the real reasoning provider behind it.

Do not leave `deepseek_native_prompt` as only a diagnostic bridge.

### 2. Fresh-state reasoning

Feed normalized Accessibility observation into DeepSeek and have it produce a structured next decision/action.

### 3. Action resolution

Resolve model intent against the current UI state. Never let a stale model output directly become a blind tap.

### 4. Verify/replan

After every meaningful action:

`observe → compare/interpret → verify → continue or replan`

### 5. Gemini Vision

Add a clean visual-observation boundary. Invoke Gemini only when screenshots add information that structured accessibility state does not provide.

### 6. Persistent task runtime

Introduce long-running task state and deadline handling.

### 7. Background/resume execution

Handle Android process death, waiting periods, network interruptions, and resumption from persisted task state.

### 8. Assistant surface

Build the user-facing Nova assistant experience.

### 9. Home/assistant integration

Investigate making Nova the Android assistant invoked by holding Home.

## Real-device testing discipline

The phone is the final authority.

Preferred cycle:

```text
inspect
  ↓
one coherent change
  ↓
pytest
  ↓
build
  ↓
install on TECNO
  ↓
real-device test
  ↓
inspect logs/state
  ↓
checkpoint
```

Do not trust only unit tests for Android behavior.

## Useful diagnostic commands

Native cold-start round trip:

```bash
am force-stop com.deepseek.chat
printf '%s\n' '{"command":"deepseek_native_prompt","prompt":"Reply with exactly COLD_NATIVE_OK"}' | nc 127.0.0.1 18765
```

Relevant log filter:

```bash
logcat -d -s NovaBridgeServer:* NovaDeepSeekHook:* | grep -E 'DEEPSEEK_NATIVE|DEEPSEEK_RESPONSE|DEEPSEEK_BRIDGE|BOOTSTRAP'
```

Useful expected markers:

- `DEEPSEEK_NATIVE_BOOTSTRAP_STARTED`
- `DEEPSEEK_NATIVE_SESSION_WAIT_BEGIN`
- `DEEPSEEK_NATIVE_SESSION_WAIT_READY`
- `DEEPSEEK_NATIVE_U_CALLING`
- `DEEPSEEK_NATIVE_U_RETURNED`
- `DEEPSEEK_STREAM_EVENT`
- `DEEPSEEK_RESPONSE_STARTED`
- `DEEPSEEK_RESPONSE_FRAGMENT`
- `DEEPSEEK_RESPONSE_FINISHED`

## Version caveat

The supplied reverse-engineering APK was DeepSeek 2.5.1.

The installed phone app during the latest tests is DeepSeek 2.5.2 (versionCode 274, targetSdk 36).

The working native cold-start test was performed against the installed app. If DeepSeek updates again, revalidate the hooked class/method/session chain before assuming internals are unchanged.

## Historical investigation facts

Important previously discovered points:

- AndroidX `InitializationProvider` is not a viable external cold-start mechanism.
- DeepSeek has no useful exported DeepSeek-specific background service for this purpose.
- `ShareResultReceiver` is a share-result callback, not a startup mechanism.
- `MainActivity` is exported and is a proven process/session bootstrap trigger.
- `ActivityOptions.setAvoidMoveToFront` was attempted for DeepSeek bootstrap and is used when available.
- Android still permits a brief visual foreground interval.
- There is only one physical display on the tested device, so a secondary-display workaround is not available.
- The proven bootstrap trigger is the explicit MainActivity.
- The native session is created through the normal DeepSeek application/Compose startup path; Nova does not manually fabricate the session.

## What NOT to do next

- Do not spend the next phase trying to make the cold-start flash mathematically zero.
- Do not add multiple general-purpose providers unless a real requirement appears.
- Do not turn DeepSeek into a direct HTTP client.
- Do not bypass authentication/security.
- Do not replace adaptive observation with fixed tap sequences.
- Do not make Gemini the main reasoning model.
- Do not build Home-button integration before the agent runtime is actually useful.

## Immediate next milestone

**Make a normal Nova goal use DeepSeek Native as its reasoning engine.**

The current native round-trip is already proven. The next work is integration, not more reverse-engineering for its own sake.
