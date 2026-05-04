"""Manages device WebSocket connections and terminal session relay."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class DeviceConnection:
    ws: WebSocket
    thing_name: str
    group_id: str
    dev_id: str


@dataclass
class TerminalSession:
    session_id: str
    browser_ws: WebSocket
    thing_name: str
    group_id: str


class ConnectionManager:
    def __init__(self) -> None:
        self.devices: dict[str, DeviceConnection] = {}  # thing_name -> DeviceConnection
        self.terminals: dict[str, TerminalSession] = {}  # session_id -> TerminalSession
        self.device_terminals: dict[str, set[str]] = {}  # thing_name -> set of session_ids

    def register_device(self, thing_name: str, ws: WebSocket, group_id: str, dev_id: str) -> None:
        self.devices[thing_name] = DeviceConnection(ws=ws, thing_name=thing_name, group_id=group_id, dev_id=dev_id)
        self.device_terminals.setdefault(thing_name, set())
        logger.info("Device connected: %s", thing_name)

    def unregister_device(self, thing_name: str) -> set[str]:
        """Remove device and return session_ids that were active on it."""
        self.devices.pop(thing_name, None)
        session_ids = self.device_terminals.pop(thing_name, set())
        for sid in session_ids:
            self.terminals.pop(sid, None)
        logger.info("Device disconnected: %s (closed %d sessions)", thing_name, len(session_ids))
        return session_ids

    def is_online(self, thing_name: str) -> bool:
        return thing_name in self.devices

    def get_device_ws(self, thing_name: str) -> WebSocket | None:
        conn = self.devices.get(thing_name)
        return conn.ws if conn else None

    def create_session(self, browser_ws: WebSocket, thing_name: str, group_id: str) -> str:
        session_id = str(uuid.uuid4())
        self.terminals[session_id] = TerminalSession(
            session_id=session_id, browser_ws=browser_ws, thing_name=thing_name, group_id=group_id,
        )
        self.device_terminals.setdefault(thing_name, set()).add(session_id)
        logger.info("Terminal session opened: %s on %s", session_id, thing_name)
        return session_id

    def remove_session(self, session_id: str) -> str | None:
        """Remove session. Returns thing_name or None."""
        session = self.terminals.pop(session_id, None)
        if not session:
            return None
        sessions = self.device_terminals.get(session.thing_name)
        if sessions:
            sessions.discard(session_id)
        logger.info("Terminal session closed: %s", session_id)
        return session.thing_name

    def get_browser_ws(self, session_id: str) -> WebSocket | None:
        session = self.terminals.get(session_id)
        return session.browser_ws if session else None


manager = ConnectionManager()
