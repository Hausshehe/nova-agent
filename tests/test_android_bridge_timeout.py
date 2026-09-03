from __future__ import annotations

import socket
import threading

import pytest

from agent.android_bridge import AndroidBridge, AndroidBridgeError


def _silent_server(listener: socket.socket) -> None:
    try:
        connection, _ = listener.accept()
        with connection:
            connection.recv(4096)
            threading.Event().wait(1.0)
    finally:
        listener.close()


def test_request_times_out_when_server_sends_no_response() -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    thread = threading.Thread(target=_silent_server, args=(listener,), daemon=True)
    thread.start()

    bridge = AndroidBridge(port=port, timeout=0.2)
    with pytest.raises(AndroidBridgeError, match="response timed out"):
        bridge._request({"command": "observe"})

    thread.join(timeout=0.5)
