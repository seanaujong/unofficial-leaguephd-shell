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
import html
import json
import logging
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QLabel, QMainWindow

from . import APP_NAME, __version__, lcu, updates
from .controller import DraftController
from .phases import Phase

log = logging.getLogger(__name__)

# League PhD's logo (the leaguephd.com favicon), in the multi-size version from
# leaguephd-app's assets/icon.ico (GPL-3.0). Used to show which site this app is for;
# the app itself is unofficial.
ICON_PATH = Path(__file__).with_name("icon.ico")
# Set on a page we're about to replace, so it can't be mistaken for its replacement.
STALE_MARKER = "__leaguephdShellStale"
READY_PROBE = f"""(() => {{
  if (window.{STALE_MARKER}) return 'stale';
  if (typeof app_call === 'function') return 'ready';
  return document.readyState === 'complete' ? 'no-hook' : 'loading';
}})()"""
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


class UpdateChecker(QObject):
    """Runs the one-off update check on a daemon thread; emits `found` if there's a newer release."""

    found = Signal(object)  # updates.Update

    def __init__(self, current_version: str):
        super().__init__()
        self._current = current_version

    def start(self) -> None:
        threading.Thread(target=self._run, name="update-check", daemon=True).start()

    def _run(self) -> None:
        update = updates.check_for_update(self._current)
        if update:
            log.info("update available: v%s", update.version)
            self.found.emit(update)


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
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(1200, 930)

        self.view = QWebEngineView(self)
        self.view.setPage(SitePage(self.view))
        self.setCentralWidget(self.view)

        # leaguephd.com can take 10+ seconds to load (it's ad-heavy). Say so,
        # rather than leave an empty window.
        self._loading = QLabel()
        self.statusBar().addPermanentWidget(self._loading)
        self._update = QLabel()  # filled by show_update; opens the release page in the browser
        self._update.setOpenExternalLinks(True)
        self.statusBar().addPermanentWidget(self._update)
        self.statusBar().addPermanentWidget(QLabel(f"v{__version__}"))

        # All draft logic lives in the controller; this window is its PageDriver.
        self.controller = DraftController(page=self, on_phase=self._show_phase)
        self._warned_generation = -1

        self.view.loadStarted.connect(self.controller.page_load_started)
        self.view.loadProgress.connect(self._on_load_progress)
        self.view.loadFinished.connect(self._on_load_finished)
        bridge.phase.connect(self.controller.connection_phase)
        bridge.session.connect(self.controller.session_event)

        # Qt doesn't always report loads in start/finish pairs, so instead of
        # relying on them, keep asking the page whether it's ready until it is.
        self._poll = QTimer(self)
        self._poll.setInterval(500)
        self._poll.timeout.connect(self._check_page_ready)
        self._poll.start()

        self.view.load(PICK_NOW_URL)

    # --- PageDriver (requests from the controller) ---------------------------

    def load_pick_now(self) -> None:
        # Mark the current document so readiness checks can tell it from the new one.
        self.view.page().runJavaScript(f"window.{STALE_MARKER} = true;")
        self.view.load(PICK_NOW_URL)

    def app_call(self, payload: dict) -> None:
        self.view.page().runJavaScript(f"app_call({json.dumps(payload)});")

    def on_pick_now(self) -> bool:
        return _is_pick_now(self.view.url())

    # --- Qt signals -> controller -------------------------------------------

    def _show_phase(self, phase: Phase) -> None:
        self.statusBar().showMessage(phase.label)

    def show_update(self, update: "updates.Update") -> None:
        self._update.setText(f'<a href="{html.escape(update.url, quote=True)}">'
                             f"Update available: v{html.escape(update.version)}</a>")
        self._update.setToolTip("Opens the release page in your browser")

    def _on_load_progress(self, percent: int) -> None:
        self._loading.setText(f"Loading leaguephd.com... {percent}%" if percent < 100 else "")

    def _on_load_finished(self, ok: bool) -> None:
        # Don't trust `ok`: the site's ad/tracker scripts often fail and report
        # ok=False even though the page works. Ask the page instead.
        self._loading.setText("")
        if not ok:
            log.info("loadFinished(ok=False) for %s; checking page anyway", self.view.url().toString())
        self._check_page_ready()

    def _check_page_ready(self) -> None:
        if self.controller.page_is_ready or not self.on_pick_now():
            return
        token = self.controller.probe_token()

        def on_answer(state) -> None:
            accepted = self.controller.page_ready(token, state == "ready")
            if accepted and state == "no-hook" and self._warned_generation != token:
                self._warned_generation = token
                log.warning("pick-now page has no app_call(); the site may have changed")

        self.view.page().runJavaScript(READY_PROBE, 0, on_answer)
