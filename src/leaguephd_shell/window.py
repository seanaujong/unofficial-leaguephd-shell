# SPDX-License-Identifier: GPL-3.0-only
# Based on leaguephd.py in leaguephd-app by leaguephd
# (https://github.com/leaguephd/leaguephd-app); rewritten 2026-11-04 for PySide6.

"""The desktop window: embeds leaguephd.com's pick-now page and feeds it the draft.

This module is Qt plumbing only. The decisions (phases, when to reload the page,
what to send it) live in controller.DraftController; MainWindow forwards Qt
signals to it and carries out its requests as its PageDriver.

Threading model: Qt owns the main thread. The LCU client is asyncio, so it
runs its own event loop on a background thread and talks to the window only
through Qt signals (which Qt queues safely across threads). That replaces the
original's qasync/QThreadExecutor setup.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QLabel, QMainWindow

from . import __version__, lcu
from .controller import DraftController
from .phases import Phase

log = logging.getLogger(__name__)

# League PhD logo, from leaguephd-app's assets/icon.ico (16-256 px).
ICON_PATH = Path(__file__).with_name("icon.ico")
PICK_NOW_URL = QUrl("https://www.leaguephd.com/en/stats/pick-now/")
SITE_HOST = "leaguephd.com"


def _is_site(url: QUrl) -> bool:
    host = url.host()
    return host == SITE_HOST or host.endswith("." + SITE_HOST)


def _is_pick_now(url: QUrl) -> bool:
    return _is_site(url) and url.path().rstrip("/").endswith("/pick-now")


class LcuBridge(QObject):
    """Runs the asyncio LCU loop on a daemon thread and re-emits as Qt signals."""

    phase = Signal(object)  # Phase: connection phases from the LCU loop
    session = Signal(str, object)  # event_type, session data

    def __init__(self, event_log: Path | None = None):
        super().__init__()
        self._event_log = event_log

    def start(self) -> None:
        threading.Thread(target=self._run, name="lcu", daemon=True).start()

    def _run(self) -> None:
        asyncio.run(lcu.run_forever(self.phase.emit, self._on_event))

    def _on_event(self, event: lcu.SessionEvent) -> None:
        if self._event_log:
            # Raw events, one JSON object per line: handy for replaying a draft later.
            with self._event_log.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"eventType": event.event_type, "data": event.data}) + "\n")
        self.session.emit(event.event_type, event.data)


page_log = logging.getLogger("leaguephd_shell.page")


class SitePage(QWebEnginePage):
    """Keeps leaguephd.com in the app; sends every other link to the real browser."""

    def javaScriptConsoleMessage(self, level, message, line, source):
        # The site's ads and video player log constantly. Route the page's console
        # into its own logger (hidden unless --page-logs) instead of stderr.
        page_log.debug("js: %s (%s:%d)", message, source, line)

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked and not _is_site(url):
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

    def createWindow(self, _window_type):
        # target="_blank" links: catch the URL, hand it to the system browser.
        popup = QWebEnginePage(self.profile(), self)

        def open_external(url: QUrl) -> None:
            QDesktopServices.openUrl(url)
            popup.deleteLater()

        popup.urlChanged.connect(open_external)
        return popup


class MainWindow(QMainWindow):
    def __init__(self, bridge: LcuBridge):
        super().__init__()
        self.setWindowTitle("League PhD")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(1200, 930)

        self.view = QWebEngineView(self)
        self.view.setPage(SitePage(self.view))
        self.view.loadFinished.connect(self._on_load_finished)
        self.setCentralWidget(self.view)

        self.statusBar().addPermanentWidget(QLabel(f"v{__version__}"))

        # All draft logic lives in the controller; this window is its PageDriver.
        self.controller = DraftController(page=self, on_phase=self._show_phase)
        self._load_token = 0

        self.view.loadStarted.connect(self._on_load_started)
        bridge.phase.connect(self.controller.connection_phase)
        bridge.session.connect(self.controller.session_event)

        self.load_pick_now()

    # --- PageDriver (requests from the controller) ---------------------------

    def load_pick_now(self) -> None:
        self.view.load(PICK_NOW_URL)

    def app_call(self, payload: dict) -> None:
        self.view.page().runJavaScript(f"app_call({json.dumps(payload)});")

    def on_pick_now(self) -> bool:
        return _is_pick_now(self.view.url())

    # --- Qt signals -> controller -------------------------------------------

    def _show_phase(self, phase: Phase) -> None:
        self.statusBar().showMessage(phase.label)

    def _on_load_started(self) -> None:
        self._load_token = self.controller.page_load_started()

    def _on_load_finished(self, ok: bool) -> None:
        # Don't trust `ok`: the site's ad/tracker scripts often fail and report
        # ok=False even though the page works. Instead, ask the page whether its
        # app_call hook exists.
        token = self._load_token
        if not ok:
            log.info("loadFinished(ok=False) for %s; checking page anyway", self.view.url().toString())
        if not self.on_pick_now():
            self.controller.page_ready(token, False)
            return

        def on_probe(has_hook) -> None:
            accepted = self.controller.page_ready(token, bool(has_hook))
            # A load replaced mid-way also answers "no"; only warn for the current page.
            if accepted and not has_hook:
                log.warning("pick-now page has no app_call(); the site may have changed")

        self.view.page().runJavaScript("typeof app_call === 'function'", 0, on_probe)
