# DeepSeek G6 real-device checkpoint

Date: 2026-09-16
Branch: `phase-g6-deepseek-request-probe`
Probe commit: `d45b8966713d8477d19ace6c49263b16600e2c4c`

## Verification

- `python -m pytest -q` -> **351 passed**
- `gradle :app:assembleDebug --no-daemon` -> **BUILD SUCCESSFUL**
- Debug APK installed successfully on the rooted TECNO KJ5.
- Vector injected `DeepSeekHookProbe` into `com.deepseek.chat`.
- Response hooks installed: `n63`.
- Native SSE event hook installed: `x21`.
- Request hook installed: `ir2`.

## Real-device request proof

After sending the normal DeepSeek message `request probe test`, logcat showed:

```text
DEEPSEEK_REQUEST_ENTRY requestClass=r51 timeout=null
```

The same request then produced the native DeepSeek stream, semantic response fragments, and completion signal:

```text
DEEPSEEK_RESPONSE_STARTED type=RESPONSE id=2
DEEPSEEK_RESPONSE_DELTA type=RESPONSE id=2 delta=request probe
DEEPSEEK_RESPONSE_DELTA type=RESPONSE id=2 delta= test
DEEPSEEK_RESPONSE_FINISH_SIGNAL id=2
DEEPSEEK_RESPONSE_FINISHED type=RESPONSE id=2 length=18
```

## Established architecture boundary

The real-device path is now proven in both directions:

```text
DeepSeek internal request
  -> ir2.b(h21, Long)
  -> request object r51
  -> native completion stream
  -> x21 / k09
  -> n63 semantic response fragments
  -> Nova response collector
  -> response/status=FINISHED
  -> Nova bridge
```

The next investigation is to determine how Nova can safely construct/invoke the already-proven internal request machinery directly, without requiring the DeepSeek UI to create the request first. The current probe remains observational and does not modify request behavior.
