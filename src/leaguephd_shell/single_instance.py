# SPDX-License-Identifier: GPL-3.0-only

"""Keep one copy of the app per user.

The first copy listens on a local named channel (a Windows named pipe, via Qt's
QLocalServer). A second copy connects, asks the first to show its window, and
exits, so you never get two windows or two connections to the League client.
Nothing here touches the network.
"""

from __future__ import annotations

import getpass
import logging
import re
import sys

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)


def channel_name() -> str:
    user = re.sub(r"[^A-Za-z0-9_-]", "_", getpass.getuser() or "user")
    return f"unofficial-leaguephd-shell-{user}"


def ask_running_copy_to_show(name: str | None = None, timeout_ms: int = 500) -> bool:
    """True if another copy is running (and was asked to show its window)."""
    if sys.platform == "win32":
        # Windows only lets the foreground process hand focus to another one.
        # We were just launched by the user, so grant it to the running copy.
        import ctypes
        ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
    socket = QLocalSocket()
    socket.connectToServer(name or channel_name())
    if not socket.waitForConnected(timeout_ms):
        return False
    socket.write(b"show")
    socket.flush()
    socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    return True


class InstanceServer(QObject):
    """Listens for later copies; emits `show_requested` when one starts."""

    show_requested = Signal()

    def __init__(self, name: str | None = None):
        super().__init__()
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)
        self._name = name or channel_name()

    def listen(self) -> bool:
        if self._server.listen(self._name):
            return True
        # Can happen if two copies start at the same instant; carry on anyway.
        log.info("single-instance channel unavailable: %s", self._server.errorString())
        return False

    def _on_connection(self) -> None:
        while self._server.hasPendingConnections():
            conn = self._server.nextPendingConnection()
            conn.disconnected.connect(conn.deleteLater)
            self.show_requested.emit()
