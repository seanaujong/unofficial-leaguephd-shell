# SPDX-License-Identifier: GPL-3.0-only
# Based on leaguephd.py in leaguephd-app by leaguephd
# (https://github.com/leaguephd/leaguephd-app); rewritten 2026-11-04 for PySide6.

"""The desktop window: embeds leaguephd.com's pick-now page and feeds it the draft.

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
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QLabel, QMainWindow

from . import __version__, lcu
from .champselect import ChampSelect

log = logging.getLogger(__name__)

PICK_NOW_URL = QUrl("https://www.leaguephd.com/en/stats/pick-now/")
SITE_HOST = "leaguephd.com"


def _is_site(url: QUrl) -> bool:
    host = url.host()
    return host == SITE_HOST or host.endswith("." + SITE_HOST)


def _is_pick_now(url: QUrl) -> bool:
    return _is_site(url) and url.path().rstrip("/").endswith("/pick-now")


class LcuBridge(QObject):
    """Runs the asyncio LCU loop on a daemon thread and re-emits as Qt signals."""

    status = Signal(str)
    session = Signal(str, object)  # event_type, session data

    def __init__(self, event_log: Path | None = None):
        super().__init__()
        self._event_log = event_log

    def start(self) -> None:
        threading.Thread(target=self._run, name="lcu", daemon=True).start()

    def _run(self) -> None:
        asyncio.run(lcu.run_forever(self.status.emit, self._on_event))

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
        self.resize(1200, 930)

        self.view = QWebEngineView(self)
        self.view.setPage(SitePage(self.view))
        self.view.loadFinished.connect(self._on_load_finished)
        self.setCentralWidget(self.view)

        self.statusBar().addPermanentWidget(QLabel(f"v{__version__}"))
        self.statusBar().showMessage("Waiting for the League client...")

        self.tracker = ChampSelect()
        self._page_ready = False
        self._pending: list[dict] = []  # payloads waiting for the page to load
        self._needs_fresh_page = True  # the page is stateful; each draft needs a clean load

        bridge.status.connect(self.statusBar().showMessage)
        bridge.session.connect(self._on_session)

        self.view.load(PICK_NOW_URL)

    def _on_session(self, event_type: str, data: dict | None) -> None:
        if event_type == "Delete" or data is None:
            self._needs_fresh_page = True
            self.statusBar().showMessage("Champ select ended")
            return
        if event_type == "Create":
            self._needs_fresh_page = True

        # New draft, or the user browsed away from pick-now mid-draft: reload the
        # page and rebuild state from this snapshot. LCU snapshots are complete,
        # so nothing is lost by starting over.
        if self._needs_fresh_page or not _is_pick_now(self.view.url()):
            self._needs_fresh_page = False
            self.tracker.reset()
            self._pending.clear()
            self._page_ready = False
            self.view.load(PICK_NOW_URL)

        self.statusBar().showMessage("In champ select")
        changed, delta = self.tracker.update(data)
        if changed:
            self._send(self.tracker.payload(delta))

    def _send(self, payload: dict) -> None:
        if not self._page_ready:
            self._pending.append(payload)
            return
        self.view.page().runJavaScript(f"app_call({json.dumps(payload)});")

    def _on_load_finished(self, ok: bool) -> None:
        # Don't trust `ok`: the site's ad/tracker scripts often fail and report
        # ok=False even though the page works. Instead, ask the page whether its
        # app_call hook exists.
        if not ok:
            log.info("loadFinished(ok=False) for %s; checking page anyway", self.view.url().toString())
        if not _is_pick_now(self.view.url()):
            self._page_ready = False
            return
        self.view.page().runJavaScript("typeof app_call === 'function'", 0, self._on_page_probe)

    def _on_page_probe(self, has_hook) -> None:
        self._page_ready = bool(has_hook)
        if not self._page_ready:
            log.warning("pick-now page has no app_call(); the site may have changed")
            return
        pending, self._pending = self._pending, []
        for payload in pending:
            self._send(payload)
