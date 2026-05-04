"""WebSocket endpoint for browser terminal sessions.

Protocol:
  1. Browser connects to /ws/terminal/{thing_name}?token=<jwt>
  2. Backend verifies JWT and device access
  3. Backend creates a session and tells the device to open a PTY
  4. Binary frames from browser = keystrokes → forwarded to device
  5. Text frames from browser = control (resize) → forwarded to device
  6. Binary frames from device = PTY output → forwarded to browser
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from auth import decode_token_raw
from connection_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()

DEFAULT_COLS = 80
DEFAULT_ROWS = 24


@router.websocket("/ws/terminal/{thing_name}")
async def terminal_websocket(ws: WebSocket, thing_name: str) -> None:
    # Step 1: Auth via query param
    token = ws.query_params.get("token")
    if not token:
        await ws.close(code=4001, reason="Missing token")
        return

    group_id = decode_token_raw(token)
    if not group_id:
        await ws.close(code=4001, reason="Invalid or expired token")
        return

    # Step 2: Verify device access
    parts = thing_name.split(":", 1)
    if len(parts) != 2 or parts[0] != group_id:
        await ws.close(code=4003, reason="Device not in your group")
        return

    # Step 3: Check device is online
    device_ws = manager.get_device_ws(thing_name)
    if not device_ws:
        await ws.close(code=4004, reason="Device is offline")
        return

    await ws.accept()

    # Step 4: Create session and notify device
    session_id = manager.create_session(ws, thing_name, group_id)

    try:
        # Tell device to open a PTY
        await device_ws.send_text(json.dumps({
            "type": "terminal_open",
            "session_id": session_id,
            "cols": DEFAULT_COLS,
            "rows": DEFAULT_ROWS,
        }))

        # Step 5: Relay loop
        while True:
            message = await ws.receive()

            if message["type"] == "websocket.receive":
                # Re-fetch device ws in case it changed
                dev_ws = manager.get_device_ws(thing_name)
                if not dev_ws:
                    await ws.send_text(json.dumps({"type": "error", "message": "Device disconnected"}))
                    break

                if "bytes" in message:
                    # Keyboard input from browser → prefix with session_id → send to device
                    payload = session_id.encode("ascii") + message["bytes"]
                    await dev_ws.send_bytes(payload)

                elif "text" in message:
                    # Control message (resize, etc.)
                    data = json.loads(message["text"])
                    if data.get("type") == "resize":
                        await dev_ws.send_text(json.dumps({
                            "type": "terminal_resize",
                            "session_id": session_id,
                            "cols": data.get("cols", DEFAULT_COLS),
                            "rows": data.get("rows", DEFAULT_ROWS),
                        }))

            elif message["type"] == "websocket.disconnect":
                break

    except WebSocketDisconnect:
        pass
    finally:
        thing = manager.remove_session(session_id)
        if thing:
            dev_ws = manager.get_device_ws(thing)
            if dev_ws:
                try:
                    await dev_ws.send_text(json.dumps({
                        "type": "terminal_close",
                        "session_id": session_id,
                    }))
                except Exception:
                    pass
