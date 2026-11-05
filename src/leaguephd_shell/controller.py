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
    page_load_started()              the page began a navigation (if Qt says so)
    probe_token() -> token           take before asking the page if it's ready
    page_ready(token, ready)         the answer: does this page have app_call()?

Outputs (requested of the PageDriver):
    load_pick_now()                  replace the page with a fresh pick-now page
    app_call(payload)                deliver one draft update to the page
    on_pick_now()                    is the page currently on pick-now?

Page readiness does not depend on Qt's load signals arriving in pairs. Qt
merges a load requested while another is in progress and then reports only one
"finished", with no new "started". So the window re-asks the page until it's
ready, and each answer carries the token from when it was asked: answers asked
before a reload we requested are stale and ignored.
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
    def __init__(
        self,
        page: PageDriver,
        on_phase: Callable[[Phase], None] = lambda _: None,
        on_unknown_champions: Callable[[set[int]], None] = lambda _: None,
    ):
        self.page = page
        self.on_phase = on_phase
        self.on_unknown_champions = on_unknown_champions
        # Champion IDs the current page has data for (None = not reported). The
        # site lags behind new releases, and its page code crashes on an ID it
        # doesn't know, so updates are adapted to this set before delivery.
        self.known_champions: frozenset[int] | None = None
        self.unknown_champions: set[int] = set()  # left out this draft
        self.phase: Phase | None = None
        self.tracker = ChampSelect()
        self.pending: list[dict] = []  # payloads waiting for the page to be ready
        self.page_is_ready = False
        self.needs_fresh_draft = True  # next snapshot starts a new draft
        # Has the current page received any draft data? The page is stateful, so
        # a used page must be reloaded for a new draft; an unused one needn't be.
        self.page_dirty = False
        self.loads_requested = 0
        # Bumped whenever the page is (or may be) replaced; readiness answers
        # asked under an older generation are stale.
        self._generation = 0
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
            self.needs_fresh_draft = True
            self._set_phase(Phase.IDLE)
            return
        if event_type == "Create":
            self.needs_fresh_draft = True

        self._set_phase(Phase.from_session(data))

        if self.needs_fresh_draft:
            self._start_fresh_draft()
        elif not self.page.on_pick_now():
            # The user browsed away mid-draft. LCU snapshots are complete, so
            # rebuild the draft from this one onto a fresh pick-now page.
            self._start_fresh_draft()

        changed, delta = self.tracker.update(data)
        if changed:
            self._send(self.tracker.payload(delta))

    def _start_fresh_draft(self) -> None:
        self.needs_fresh_draft = False
        self.tracker.reset()
        self.pending.clear()
        if self.unknown_champions:
            self.unknown_champions = set()
            self.on_unknown_champions(set())
        if self.page_dirty or not self.page.on_pick_now():
            self._reload_page()
        # Otherwise the current page (perhaps still loading) is unused: keep it.
        # Reloading it would only restart a slow load.

    def _reload_page(self) -> None:
        self._generation += 1  # answers about the old page are now stale
        self.page_is_ready = False
        self.page_dirty = False
        self.loads_requested += 1
        self.page.load_pick_now()

    # --- page delivery ------------------------------------------------------

    def _send(self, payload: dict) -> None:
        if self.page_is_ready:
            self.page_dirty = True
            self.page.app_call(self._fit_to_page(payload))
        else:
            self.pending.append(payload)

    def _fit_to_page(self, payload: dict) -> dict:
        """Replace champions the page doesn't know, so its code doesn't crash.

        Unknown bans become -1 (the page's "no ban" portrait); unknown picks are
        left out, so the page still suggests picks for the rest of the draft.
        """
        known = self.known_champions
        if known is None:
            return payload
        unknown: set[int] = set()

        def ok(champion_id) -> bool:
            if champion_id is None or champion_id in known:
                return True
            unknown.add(champion_id)
            return False

        fitted = {
            **payload,
            "bans": [b if ok(b) else -1 for b in payload["bans"]],
            "picks": [[s if ok(s["champion_id"]) else {**s, "champion_id": None} for s in team]
                      for team in payload["picks"]],
            "updated": {
                **payload["updated"],
                "insert_list": [i for i in payload["updated"]["insert_list"] if ok(i["champion_id"])],
            },
        }
        if not unknown <= self.unknown_champions:
            self.unknown_champions |= unknown
            log.warning("leaguephd.com doesn't know champion(s) %s; left out", sorted(self.unknown_champions))
            self.on_unknown_champions(set(self.unknown_champions))
        return fitted

    def page_load_started(self) -> None:
        """The page started a navigation (ours, or the user clicking a link).

        Doesn't clear ``page_dirty``: a navigation within the same document
        keeps its draft state, so only a load we requested counts as fresh.
        """
        self._generation += 1
        self.page_is_ready = False

    def probe_token(self) -> int:
        """Take this before asking the page whether it's ready."""
        return self._generation

    def page_ready(self, token: int, ready: bool, known_champions=None) -> bool:
        """The page's answer to a readiness check made under ``token``.

        ``known_champions``: the champion IDs the page has data for, if it said.
        Returns False if the answer is stale (the page was replaced since) and
        was ignored.
        """
        if token != self._generation:
            log.debug("ignoring stale readiness answer (token %d, now %d)", token, self._generation)
            return False
        if known_champions is not None:
            self.known_champions = frozenset(int(c) for c in known_champions)
        if ready and not self.page_is_ready:
            self.page_is_ready = True
            pending, self.pending = self.pending, []
            for payload in pending:
                self._send(payload)
        elif not ready:
            self.page_is_ready = False
        return True
