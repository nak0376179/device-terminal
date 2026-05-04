"""Device agent: connects to backend via WebSocket and provides PTY shell access.

Usage:
    python device_agent.py              # uses config.json in current directory
    python device_agent.py config.json  # explicit config path
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import pty
import signal
import struct
import subprocess
import sys
import termios

import websockets
import websockets.asyncio.client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

RECONNECT_BASE_SEC = 1
RECONNECT_MAX_SEC = 30
PTY_READ_SIZE = 4096
SHELL = os.environ.get("SHELL", "/bin/bash")


class PtySession:
    """Manages a single PTY session."""

    def __init__(self, session_id: str, cols: int = 80, rows: int = 24) -> None:
        self.session_id = session_id
        self.master_fd: int | None = None
        self.pid: int | None = None
        self.reader_task: asyncio.Task | None = None
        self._cols = cols
        self._rows = rows

    def spawn(self) -> None:
        """Fork a PTY and exec a shell."""
        pid, fd = pty.fork()

        if pid == 0:
            # Child process
            os.execvp(SHELL, [SHELL])
            # unreachable
        else:
            # Parent process
            self.pid = pid
            self.master_fd = fd

            # Set initial size
            self._set_winsize(self._cols, self._rows)

            # Make master fd non-blocking
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def _set_winsize(self, cols: int, rows: int) -> None:
        if self.master_fd is not None:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
            self._cols = cols
            self._rows = rows

    def resize(self, cols: int, rows: int) -> None:
        self._set_winsize(cols, rows)

    def write(self, data: bytes) -> None:
        if self.master_fd is not None:
            os.write(self.master_fd, data)

    def close(self) -> None:
        if self.reader_task and not self.reader_task.done():
            self.reader_task.cancel()
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None
        if self.pid is not None:
            try:
                os.kill(self.pid, signal.SIGTERM)
                os.waitpid(self.pid, os.WNOHANG)
            except (OSError, ChildProcessError):
                pass
            self.pid = None


class DeviceAgent:
    """WebSocket client that connects to the backend and manages PTY sessions."""

    def __init__(self, config: dict) -> None:
        self.thing_name = config["thing_name"]
        self.api_key = config["api_key"]
        self.ws_url = config["backend_ws_url"]
        self.sessions: dict[str, PtySession] = {}
        self._ws: websockets.asyncio.client.ClientConnection | None = None
        self._stop = asyncio.Event()

    async def run(self) -> None:
        """Main loop with reconnection."""
        delay = RECONNECT_BASE_SEC
        while not self._stop.is_set():
            try:
                await self._connect_and_serve()
                delay = RECONNECT_BASE_SEC
            except (ConnectionError, websockets.exceptions.ConnectionClosed, OSError) as e:
                logger.warning("Connection lost: %s. Reconnecting in %ds...", e, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_SEC)
            except asyncio.CancelledError:
                break

        self._cleanup_all_sessions()

    async def _connect_and_serve(self) -> None:
        logger.info("Connecting to %s ...", self.ws_url)
        async with websockets.asyncio.client.connect(self.ws_url) as ws:
            self._ws = ws

            # Authenticate
            await ws.send(json.dumps({"type": "auth", "api_key": self.api_key}))
            logger.info("Connected and authenticated as %s", self.thing_name)

            # Receive loop
            async for message in ws:
                if isinstance(message, str):
                    await self._handle_control(json.loads(message))
                elif isinstance(message, bytes):
                    self._handle_binary(message)

        self._ws = None

    async def _handle_control(self, data: dict) -> None:
        msg_type = data.get("type")
        session_id = data.get("session_id", "")

        if msg_type == "terminal_open":
            cols = data.get("cols", 80)
            rows = data.get("rows", 24)
            await self._open_terminal(session_id, cols, rows)

        elif msg_type == "terminal_close":
            self._close_terminal(session_id)

        elif msg_type == "terminal_resize":
            session = self.sessions.get(session_id)
            if session:
                session.resize(data.get("cols", 80), data.get("rows", 24))

    def _handle_binary(self, raw: bytes) -> None:
        """Receive keyboard input: <session_id:36><data>."""
        if len(raw) < 36:
            return
        session_id = raw[:36].decode("ascii", errors="ignore")
        data = raw[36:]
        session = self.sessions.get(session_id)
        if session:
            try:
                session.write(data)
            except OSError:
                self._close_terminal(session_id)

    async def _open_terminal(self, session_id: str, cols: int, rows: int) -> None:
        logger.info("Opening terminal session: %s (%dx%d)", session_id, cols, rows)

        session = PtySession(session_id, cols, rows)
        session.spawn()
        self.sessions[session_id] = session

        # Start reading PTY output
        session.reader_task = asyncio.create_task(self._pty_reader(session))

        # ACK
        if self._ws:
            await self._ws.send(json.dumps({
                "type": "terminal_opened",
                "session_id": session_id,
            }))

    async def _pty_reader(self, session: PtySession) -> None:
        """Read PTY output and send to backend as binary frames."""
        loop = asyncio.get_event_loop()
        prefix = session.session_id.encode("ascii")
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()

        def _readable_cb():
            try:
                data = os.read(session.master_fd, PTY_READ_SIZE)
                queue.put_nowait(data if data else None)
            except OSError:
                queue.put_nowait(None)

        if session.master_fd is not None:
            loop.add_reader(session.master_fd, _readable_cb)

        try:
            while True:
                data = await queue.get()
                if data is None:
                    break
                if self._ws:
                    await self._ws.send(prefix + data)

        except asyncio.CancelledError:
            return
        finally:
            if session.master_fd is not None:
                try:
                    loop.remove_reader(session.master_fd)
                except Exception:
                    pass
            exit_code = self._wait_child(session.pid)
            self.sessions.pop(session.session_id, None)
            session.close()

            if self._ws:
                try:
                    await self._ws.send(json.dumps({
                        "type": "terminal_closed",
                        "session_id": session.session_id,
                        "exit_code": exit_code,
                    }))
                except Exception:
                    pass

            logger.info("Terminal session ended: %s (exit=%s)", session.session_id, exit_code)

    @staticmethod
    def _wait_child(pid: int | None) -> int:  # noqa: D102
        if pid is None:
            return -1
        try:
            _, status = os.waitpid(pid, 0)
            if os.WIFEXITED(status):
                return os.WEXITSTATUS(status)
            return -1
        except ChildProcessError:
            return -1

    def _close_terminal(self, session_id: str) -> None:
        session = self.sessions.pop(session_id, None)
        if session:
            session.close()
            logger.info("Closed terminal session: %s", session_id)

    def _cleanup_all_sessions(self) -> None:
        for session in list(self.sessions.values()):
            session.close()
        self.sessions.clear()

    def stop(self) -> None:
        self._stop.set()


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"

    if not os.path.exists(config_path):
        logger.error("Config file not found: %s", config_path)
        logger.error("Run 'make init-local' first to generate config.json")
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    for key in ("thing_name", "api_key", "backend_ws_url"):
        if key not in config:
            logger.error("Missing key in config: %s", key)
            sys.exit(1)

    agent = DeviceAgent(config)

    loop = asyncio.new_event_loop()

    def _signal_handler():
        logger.info("Shutting down...")
        agent.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    try:
        loop.run_until_complete(agent.run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
