"""Replay a real recorded ranked draft through the app's real DraftController.

No Qt, browser, network or delays: a FakePage stands in for the pick-now page.
Fixture: tests/fixtures/ranked_draft.jsonl, made from a --debug recording with
scripts/scrub_recording.py. 92 events: PLANNING -> BANNING -> PICKING ->
FINALIZATION -> GAME_STARTING, then Delete when the game loads.

FakePage models what QWebEngineView was observed to do, not an idealised
version: loads take a while, a load requested while another is running is
merged into it and reports no new "load started", and "load started" may
arrive late or not at all. The window copes by polling readiness, so the
tests poll too.
"""

import json
from pathlib import Path

from leaguephd_shell.controller import DraftController
from leaguephd_shell.lcu import diff_sessions
from leaguephd_shell.phases import Phase

FIXTURE = Path(__file__).parent / "fixtures" / "ranked_draft.jsonl"


def load_events():
    return [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]


class Doc:
    """One page document: loading until finished; marked stale when we replace it."""

    def __init__(self):
        self.loaded = False
        self.stale = False
        self.received: list[dict] = []  # app_call payloads delivered to this document

    def answer(self):
        if self.stale:
            return "stale"
        return "ready" if self.loaded else "loading"


class FakePage:
    def __init__(self, signals_load_started=True):
        self.controller: DraftController | None = None
        self.signals_load_started = signals_load_started
        self.doc = Doc()  # the window starts its own first load
        self.docs = [self.doc]
        self.url_is_pick_now = True

    # PageDriver
    def load_pick_now(self):
        self.doc.stale = True  # what the window's stale marker does
        # Whether or not a load was already running (Qt merges them), the page
        # ends up in a fresh, still-loading document.
        self.doc = Doc()
        self.docs.append(self.doc)
        self.url_is_pick_now = True
        if self.signals_load_started:
            self.controller.page_load_started()

    def app_call(self, payload):
        self.doc.received.append(json.loads(json.dumps(payload)))  # must round-trip to JS

    def on_pick_now(self):
        return self.url_is_pick_now

    # test controls
    def finish_load(self):
        self.doc.loaded = True
        self.poll()

    def poll(self):
        """What the window's 500 ms readiness check does."""
        token = self.controller.probe_token()
        self.controller.page_ready(token, self.doc.answer() == "ready")

    @property
    def delivered(self):
        return self.doc.received


def make(signals_load_started=True):
    page = FakePage(signals_load_started)
    phases = []
    ctrl = DraftController(page, on_phase=phases.append)
    page.controller = ctrl
    return ctrl, page, phases


def play(ctrl, page, events, load_lag=3):
    """Feed events, polling like the window; a loading page finishes `load_lag` events later."""
    waited = 0
    for event in events:
        ctrl.session_event(event["eventType"], event["data"])
        if not page.doc.loaded:
            waited += 1
            if waited > load_lag:
                page.finish_load()
                waited = 0
        page.poll()
    page.finish_load()


def test_phases_in_order():
    ctrl, page, phases = make()
    play(ctrl, page, load_events())
    assert phases == [
        Phase.WAITING_FOR_CLIENT, Phase.PLANNING, Phase.BANNING, Phase.PICKING,
        Phase.FINALIZATION, Phase.GAME_STARTING, Phase.IDLE,
    ]


def test_full_draft_reaches_page():
    ctrl, page, _ = make()
    play(ctrl, page, load_events())
    assert ctrl.loads_requested == 0, "the startup page was unused, so it is used as is"
    assert not ctrl.pending, "everything queued during the load was delivered"
    assert ctrl.tracker.num_banned == 10 and ctrl.tracker.num_picked == 10

    to_pick = [p for p in page.delivered if p["updated"]["to_pick_phase"]]
    assert len(to_pick) == 1, "the page must be told to enter pick phase exactly once"

    inserts = [i for p in page.delivered for i in p["updated"]["insert_list"]]
    assert len(inserts) == 10, "each of the 10 picks is sent to the page exactly once"
    assert {(i["side"], i["slot"]) for i in inserts} == {(s, n) for s in (0, 1) for n in range(5)}
    my_side = ctrl.tracker.my_side
    assert all(i["role"] for i in inserts if i["side"] == my_side), "allies carry their role"
    assert not any(i["role"] for i in inserts if i["side"] != my_side), "enemy roles are unknown"


def test_second_draft_matches_first():
    """Same controller, two drafts back to back: draft 2 must not inherit draft 1's state."""
    events = load_events()
    second = [{**events[0], "eventType": "Create"}, *events[1:]]
    ctrl, page, phases = make()
    play(ctrl, page, events)
    first = list(page.delivered)
    play(ctrl, page, second)
    assert ctrl.loads_requested == 1, "the used page is replaced for the second draft"
    assert page.delivered == first
    assert phases.count(Phase.PLANNING) == 2


def test_opening_mid_draft_while_page_still_loading():
    """The reported bug: app opened during champ select, site slow to load.

    The first snapshot arrives before the startup page has finished loading.
    The page must be used as is (no second load), and get the draft once loaded.
    """
    events = load_events()
    for signals in (True, False):
        ctrl, page, _ = make(signals_load_started=signals)
        ctrl.session_event("Update", events[40]["data"])  # mid-picks, page still loading
        page.poll()
        assert page.delivered == [] and ctrl.pending
        page.finish_load()
        assert ctrl.loads_requested == 0
        assert len(page.delivered) == 1 and not ctrl.pending
        sent = page.delivered[0]
        assert sent["updated"]["to_pick_phase"] and len(sent["updated"]["insert_list"]) == 3


def test_reload_without_load_started_signal_still_delivers():
    """Qt may report no 'load started' for our reload; polling must still find the new page."""
    events = load_events()
    second = [{**events[0], "eventType": "Create"}, *events[1:]]
    ctrl, page, _ = make(signals_load_started=False)
    play(ctrl, page, events)
    first = list(page.delivered)
    play(ctrl, page, second)
    assert ctrl.loads_requested == 1
    assert page.delivered == first


def test_page_load_speed_does_not_change_what_the_page_gets():
    instant, slow = make(), make()
    play(*instant[:2], load_events(), load_lag=0)
    play(*slow[:2], load_events(), load_lag=40)  # page still loading well into bans
    assert slow[1].delivered == instant[1].delivered


def test_stale_readiness_from_previous_page_is_ignored():
    """A readiness answer from the old page, arriving after we asked for a reload."""
    events = load_events()
    ctrl, page, _ = make(signals_load_started=False)
    play(ctrl, page, events[:30])  # page used
    token = ctrl.probe_token()  # check asked of the old page...
    ctrl.session_event("Create", events[0]["data"])  # ...then a new draft reloads it
    assert ctrl.page_ready(token, True) is False  # old page's late "ready" is rejected
    assert page.delivered == [] and ctrl.pending, "nothing sent to a page being replaced"
    page.finish_load()
    assert len(page.delivered) == 1 and not ctrl.pending


def test_stale_page_never_answers_ready():
    """Even with a fresh token, the old document answers 'stale' until it's replaced."""
    page_doc = Doc()
    page_doc.loaded, page_doc.stale = True, True
    assert page_doc.answer() == "stale"


def test_browsing_away_mid_draft_replays_onto_fresh_page():
    events = load_events()
    ctrl, page, _ = make()
    play(ctrl, page, events[:50])
    page.url_is_pick_now = False  # user clicked to another leaguephd page
    play(ctrl, page, events[50:])
    assert ctrl.loads_requested == 1
    full = make()
    play(*full[:2], events)
    final = lambda d: (d[-1]["bans"], d[-1]["picks"])
    assert final(page.delivered) == final(full[1].delivered), "fresh page rebuilt to the same draft"


def test_unused_page_is_not_reloaded_after_a_dodge():
    """Dodge before any data reached the page: the next draft keeps the same page."""
    events = load_events()
    ctrl, page, _ = make()
    ctrl.session_event("Create", events[0]["data"])  # page still loading, nothing sent
    ctrl.session_event("Delete", None)
    ctrl.session_event("Create", events[0]["data"])
    assert ctrl.loads_requested == 0
    page.finish_load()
    assert len(page.delivered) == 1


def test_reconnect_idle_does_not_hide_champ_select_phase():
    ctrl, page, _ = make()
    ctrl.session_event("Update", load_events()[30]["data"])
    ctrl.connection_phase(Phase.IDLE)
    assert ctrl.phase.in_champ_select
    ctrl.connection_phase(Phase.WAITING_FOR_CLIENT)
    assert ctrl.phase is Phase.WAITING_FOR_CLIENT


def test_polling_turns_snapshots_into_one_create_and_one_delete():
    """What the HTTP fallback would emit if it saw these snapshots, two drafts in a row."""
    snapshots = [e["data"] for e in load_events()]  # ends with None (not in champ select)
    stream = [None, *snapshots, *snapshots]
    events = [diff_sessions(a, b) for a, b in zip(stream, stream[1:])]
    types = [e.event_type for e in events if e]
    assert types.count("Create") == 2
    assert types.count("Delete") == 2
    assert types[0] == "Create" and types[-1] == "Delete"
