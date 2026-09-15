package com.hausshehe.nova;

import java.util.HashMap;
import java.util.Map;

/**
 * In-process semantic response collector for the DeepSeek hook.
 *
 * The collector deliberately does not know about Android, Xposed, logcat, or
 * the Nova bridge. It converts DeepSeek's cumulative fragment text into
 * structured lifecycle events that a later bridge adapter can consume.
 */
public final class DeepSeekResponseCollector {
    public interface Listener {
        void onResponseStarted(String type, int id);
        void onResponseDelta(String type, int id, String delta);
        void onResponseReplaced(String type, int id, String text);
        void onResponseFinished(String type, int id, String text);
    }

    private static final class State {
        final int id;
        String type;
        String text = "";
        boolean started;

        State(int id, String type) {
            this.id = id;
            this.type = type;
        }
    }

    private final Map<Integer, State> states = new HashMap<>();
    private Listener listener;

    public synchronized void setListener(Listener listener) {
        this.listener = listener;
    }

    public synchronized void append(String type, int id, String cumulativeText) {
        State state = state(type, id);
        String next = safe(cumulativeText);

        if (!state.started) {
            state.started = true;
            notifyStarted(state);
        }

        if (next.startsWith(state.text)) {
            String delta = next.substring(state.text.length());
            state.text = next;
            if (!delta.isEmpty()) {
                notifyDelta(state, delta);
            }
            return;
        }

        state.text = next;
        notifyReplace(state);
    }

    public synchronized void replace(String type, int id, String text) {
        State state = state(type, id);
        String next = safe(text);
        if (!state.started) {
            state.started = true;
            notifyStarted(state);
        }
        state.text = next;
        notifyReplace(state);
    }

    public synchronized void finish(String type, int id) {
        State state = states.remove(id);
        if (state == null || !state.started) {
            return;
        }
        Listener current = listener;
        if (current != null) {
            current.onResponseFinished(state.type, id, state.text);
        }
    }

    public synchronized void clear() {
        states.clear();
    }

    private State state(String type, int id) {
        State state = states.get(id);
        if (state == null) {
            state = new State(id, safe(type));
            states.put(id, state);
        } else if (type != null) {
            state.type = type;
        }
        return state;
    }

    private void notifyStarted(State state) {
        Listener current = listener;
        if (current != null) {
            current.onResponseStarted(state.type, state.id);
        }
    }

    private void notifyDelta(State state, String delta) {
        Listener current = listener;
        if (current != null) {
            current.onResponseDelta(state.type, state.id, delta);
        }
    }

    private void notifyReplace(State state) {
        Listener current = listener;
        if (current != null) {
            current.onResponseReplaced(state.type, state.id, state.text);
        }
    }

    private static String safe(String value) {
        return value == null ? "" : value;
    }
}
