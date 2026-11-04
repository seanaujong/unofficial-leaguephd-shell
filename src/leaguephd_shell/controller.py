# SPDX-License-Identifier: GPL-3.0-only

"""The app's draft logic, with no Qt in it.

``DraftController`` decides everything that happens between the League client
and the pick-now page: which phase we're in, when a draft starts fresh, what to
send to the page, and when the page is ready to receive it. The Qt window
(window.py) only forwards events in and carries out the controller's requests
through a ``PageDriver``. That split lets tests replay real drafts through the
exact code the app runs, with a fake page and no delays.

Inputs (called by the window):
    connection_phase(phase)          from the LCU loop: WAITING_FOR_CLIENT / IDLE
    session_event(type, data)        champ select Create / Update / Delete
    page_load_started() -> token     the page began loading (any navigation)
    page_ready(token, ready)         that load finished; does app_call() exist?

Outputs (requested of the PageDriver):
    load_pick_now()                  (re)load the pick-now page
    app_call(payload)                deliver one draft update to the page
    on_pick_now()                    is the page currently on pick-now?
"""

from __future__ import annotations

import logging
from typing import Callable, Protocol

from .champselect import ChampSelect
from .phases import Phase

log = logging.getLogger(__name__)


class PageDriver(Protocol):
    def load_pick_now(self) -> None: ...
    def app_call(self, payload: dict) -> None: ...
    def on_pick_now(self) -> bool: ...


class DraftController:
    def __init__(self, page: PageDriver, on_phase: Callable[[Phase], None] = lambda _: None):
        self.page = page
        self.on_phase = on_phase
        self.phase: Phase | None = None
        self.tracker = ChampSelect()
        self.pending: list[dict] = []  # payloads waiting for the page to be ready
        self.page_is_ready = False
        self.needs_fresh_page = True  # the page is stateful; each draft needs a clean load
        # Bumped on every load we request and every load the page starts. A
        # readiness answer for an older load is stale and must be ignored, or
        # updates would be sent to a page that's about to be replaced.
        self._load_generation = 0
        self._set_phase(Phase.WAITING_FOR_CLIENT)

    # --- phases -------------------------------------------------------------

    def _set_phase(self, phase: Phase) -> None:
        """The single place the app's phase changes. See phases.py for the diagram."""
        if phase == self.phase:
            return
        log.info("phase: %s -> %s", self.phase.name if self.phase else None, phase.name)
        self.phase = phase
        self.on_phase(phase)

    def connection_phase(self, phase: Phase) -> None:
        # The LCU loop reports IDLE on every (re)connect; don't let that
        # overwrite a champ select phase the replayed snapshot already set.
        if phase == Phase.IDLE and self.phase and self.phase.in_champ_select:
            return
        self._set_phase(phase)

    # --- champ select -------------------------------------------------------

    def session_event(self, event_type: str, data: dict | None) -> None:
        if event_type == "Delete" or data is None:
            # Champ select closed: the game loaded, or someone dodged.
            self.needs_fresh_page = True
            self._set_phase(Phase.IDLE)
            return
        if event_type == "Create":
            self.needs_fresh_page = True

        self._set_phase(Phase.from_session(data))

        # New draft, or the user browsed away from pick-now mid-draft: reload the
        # page and rebuild state from this snapshot. LCU snapshots are complete,
        # so nothing is lost by starting over.
        if self.needs_fresh_page or not self.page.on_pick_now():
            self._start_fresh_page()

        changed, delta = self.tracker.update(data)
        if changed:
            self._send(self.tracker.payload(delta))

    def _start_fresh_page(self) -> None:
        self.needs_fresh_page = False
        self.tracker.reset()
        self.pending.clear()
        self.page_is_ready = False
        self._load_generation += 1  # invalidate any readiness check still in flight
        self.page.load_pick_now()

    # --- page delivery ------------------------------------------------------

    def _send(self, payload: dict) -> None:
        if self.page_is_ready:
            self.page.app_call(payload)
        else:
            self.pending.append(payload)

    def page_load_started(self) -> int:
        """The page began loading. Returns the token to pass to page_ready."""
        self._load_generation += 1
        self.page_is_ready = False
        return self._load_generation

    def page_ready(self, token: int, ready: bool) -> bool:
        """A load finished. ``ready`` means it's pick-now and app_call() exists.

        Returns False if the answer was for a stale load and was ignored.
        """
        if token != self._load_generation:
            log.debug("ignoring readiness for stale page load %d", token)
            return False
        self.page_is_ready = ready
        if ready:
            pending, self.pending = self.pending, []
            for payload in pending:
                self.page.app_call(payload)
        return True
