"""Replay a real recorded ranked draft through the app's real DraftController.

No Qt, browser, network or delays: a FakePage stands in for the pick-now page.
Fixture: tests/fixtures/ranked_draft.jsonl, made from a --debug recording with
scripts/scrub_recording.py. 92 events: PLANNING -> BANNING -> PICKING ->
FINALIZATION -> GAME_STARTING, then Delete when the game loads.
"""

import json
from pathlib import Path

from leaguephd_shell.controller import DraftController
from leaguephd_shell.lcu import diff_sessions
from leaguephd_shell.phases import Phase

FIXTURE = Path(__file__).parent / "fixtures" / "ranked_draft.jsonl"


def load_events():
    return [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]


class FakePage:
    """Acts like the Qt window's PageDriver. Loads finish when the test says so."""

    def __init__(self):
        self.controller: DraftController | None = None
        self.loads = 0
        self.delivered: list[dict] = []  # app_call payloads, as the page received them
        self.url_is_pick_now = False
        self.load_requested = False  # asked to load; Qt hasn't emitted loadStarted yet
        self.loading_token: int | None = None

    # PageDriver
    def load_pick_now(self):
        # Like QWebEngineView.load: returns at once, loadStarted comes later.
        self.loads += 1
        self.url_is_pick_now = True
        self.load_requested = True

    def app_call(self, payload):
        self.delivered.append(json.loads(json.dumps(payload)))  # must round-trip to JS

    def on_pick_now(self):
        return self.url_is_pick_now

    # test controls
    @property
    def busy(self):
        return self.load_requested or self.loading_token is not None

    def start_load(self):
        """Qt's loadStarted signal."""
        if self.load_requested:
            self.load_requested = False
            self.loading_token = self.controller.page_load_started()

    def finish_load(self, ready=True):
        """Qt's loadFinished + the app_call probe answering."""
        self.start_load()
        if self.loading_token is not None:
            token, self.loading_token = self.loading_token, None
            self.controller.page_ready(token, ready)


def make():
    page = FakePage()
    phases = []
    ctrl = DraftController(page, on_phase=phases.append)
    page.controller = ctrl
    return ctrl, page, phases


def play(ctrl, page, events, load_lag=3):
    """Feed events; each page load finishes `load_lag` events after it starts."""
    since_load = 0
    for event in events:
        ctrl.session_event(event["eventType"], event["data"])
        page.start_load()
        if page.busy:
            since_load += 1
            if since_load > load_lag:
                page.finish_load()
                since_load = 0
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
    assert page.loads == 1
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
    page.delivered.clear()
    play(ctrl, page, second)
    assert page.loads == 2, "one fresh page per draft"
    assert page.delivered == first
    assert phases.count(Phase.PLANNING) == 2


def test_page_load_speed_does_not_change_what_the_page_gets():
    instant, slow = make(), make()
    play(*instant[:2], load_events(), load_lag=0)
    play(*slow[:2], load_events(), load_lag=40)  # page still loading well into bans
    assert slow[1].delivered == instant[1].delivered


def test_stale_readiness_from_previous_page_is_ignored():
    """The race: draft 1's page check answers after draft 2 already started reloading."""
    events = load_events()
    ctrl, page, _ = make()
    ctrl.session_event("Create", events[0]["data"])
    page.start_load()
    old_token = page.loading_token  # draft 1's page is loading...
    ctrl.session_event("Delete", None)
    ctrl.session_event("Create", events[0]["data"])  # ...draft 2 requests a reload
    assert ctrl.page_ready(old_token, True) is False  # draft 1's late "ready" is rejected
    assert page.delivered == [] and ctrl.pending, "nothing sent to a page being replaced"
    page.finish_load()
    assert len(page.delivered) == 1 and not ctrl.pending


def test_browsing_away_mid_draft_replays_onto_fresh_page():
    events = load_events()
    ctrl, page, _ = make()
    play(ctrl, page, events[:50])
    page.url_is_pick_now = False  # user clicked to another leaguephd page
    page.delivered.clear()
    play(ctrl, page, events[50:])
    assert page.loads == 2
    full = make()
    play(*full[:2], events)
    final = lambda d: (d[-1]["bans"], d[-1]["picks"])
    assert final(page.delivered) == final(full[1].delivered), "fresh page rebuilt to the same draft"


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
