"""WebSocket endpoint for device agents.

Protocol:
  1. Device connects to /ws/device
  2. First text message must be: {"type":"auth","api_key":"<uuid>"}
  3. After auth, device receives control messages (text) and terminal input (binary)
  4. Device sends control messages (text) and terminal output (binary)

Binary frame format: <session_id:36 bytes ASCII><data>
"""

from __future__ import annotations

import asyncio
import json
import logging

from boto3.dynamodb.conditions import Key
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from connection_manager import manager
from db import devices_table
from device_helpers import make_device_pk

logger = logging.getLogger(__name__)

router = APIRouter()

AUTH_TIMEOUT_SEC = 5


def _lookup_device_by_api_key(api_key: str) -> dict | None:
    resp = devices_table().query(
        IndexName="api_key-index",
        KeyConditionExpression=Key("api_key").eq(api_key),
        Limit=1,
    )
    items = resp.get("Items", [])
    return items[0] if items else None


@router.websocket("/ws/device")
async def device_websocket(ws: WebSocket) -> None:
    await ws.accept()

    # Step 1: Authenticate
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=AUTH_TIMEOUT_SEC)
        msg = json.loads(raw)
        if msg.get("type") != "auth" or not msg.get("api_key"):
            await ws.close(code=4001, reason="Invalid auth message")
            return
    except (asyncio.TimeoutError, json.JSONDecodeError):
        await ws.close(code=4001, reason="Auth timeout or invalid JSON")
        return

    device = _lookup_device_by_api_key(msg["api_key"])
    if not device:
        await ws.close(code=4001, reason="Invalid API key")
        return

    thing_name = device["thing_name"]
    group_id = device["group_id"]
    dev_id = device["dev_id"]

    manager.register_device(thing_name, ws, group_id, dev_id)

    try:
        while True:
            message = await ws.receive()

            if message["type"] == "websocket.receive":
                if "text" in message:
                    # Control message from device
                    data = json.loads(message["text"])
                    msg_type = data.get("type")
                    session_id = data.get("session_id", "")

                    if msg_type == "terminal_opened":
                        logger.info("Device ACK terminal_opened: %s", session_id)
                        browser_ws = manager.get_browser_ws(session_id)
                        if browser_ws:
                            await browser_ws.send_text(json.dumps({"type": "connected"}))

                    elif msg_type == "terminal_closed":
                        logger.info("Device reports terminal_closed: %s", session_id)
                        browser_ws = manager.get_browser_ws(session_id)
                        if browser_ws:
                            await browser_ws.send_text(json.dumps({
                                "type": "closed",
                                "exit_code": data.get("exit_code", -1),
                            }))
                            await browser_ws.close()
                        manager.remove_session(session_id)

                elif "bytes" in message:
                    # Binary: terminal output from device PTY
                    raw_bytes = message["bytes"]
                    if len(raw_bytes) < 36:
                        continue
                    session_id = raw_bytes[:36].decode("ascii", errors="ignore")
                    pty_data = raw_bytes[36:]
                    browser_ws = manager.get_browser_ws(session_id)
                    if browser_ws:
                        await browser_ws.send_bytes(pty_data)

            elif message["type"] == "websocket.disconnect":
                break

    except WebSocketDisconnect:
        pass
    finally:
        closed_sessions = manager.unregister_device(thing_name)
        for sid in closed_sessions:
            browser_ws = manager.get_browser_ws(sid)
            if browser_ws:
                try:
                    await browser_ws.send_text(json.dumps({"type": "error", "message": "Device disconnected"}))
                    await browser_ws.close()
                except Exception:
                    pass
