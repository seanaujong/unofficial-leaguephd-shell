"""Replay a real recorded ranked draft (scrubbed) with no Qt, network or delays.

Fixture: tests/fixtures/ranked_draft.jsonl, made from a --debug recording with
scripts/scrub_recording.py. 92 events: PLANNING -> BANNING -> PICKING ->
FINALIZATION -> GAME_STARTING, then Delete when the game loads.
"""

import json
from pathlib import Path

from leaguephd_shell.champselect import ChampSelect
from leaguephd_shell.lcu import diff_sessions
from leaguephd_shell.phases import Phase

FIXTURE = Path(__file__).parent / "fixtures" / "ranked_draft.jsonl"


def load_events():
    return [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]


def replay(events, tracker=None):
    """Mirror MainWindow._on_session: reset on a new draft, collect page payloads and phases."""
    tracker = tracker or ChampSelect()
    payloads, phases = [], []
    fresh = True
    for event in events:
        if event["eventType"] == "Delete" or event["data"] is None:
            fresh = True
            phases.append(Phase.IDLE)
            continue
        if event["eventType"] == "Create":
            fresh = True
        phase = Phase.from_session(event["data"])
        if not phases or phases[-1] != phase:
            phases.append(phase)
        if fresh:
            tracker.reset()
            fresh = False
        changed, delta = tracker.update(event["data"])
        if changed:
            payloads.append(json.loads(json.dumps(tracker.payload(delta))))  # must round-trip to JS
    return tracker, payloads, phases


def test_phases_in_order():
    _, _, phases = replay(load_events())
    assert phases == [
        Phase.PLANNING, Phase.BANNING, Phase.PICKING,
        Phase.FINALIZATION, Phase.GAME_STARTING, Phase.IDLE,
    ]


def test_full_draft_reaches_page():
    tracker, payloads, _ = replay(load_events())
    assert tracker.num_banned == 10 and tracker.num_picked == 10
    assert all(slot["champion_id"] for team in tracker.picks for slot in team)

    to_pick = [p for p in payloads if p["updated"]["to_pick_phase"]]
    assert len(to_pick) == 1, "the page must be told to enter pick phase exactly once"

    inserts = [i for p in payloads for i in p["updated"]["insert_list"]]
    assert len(inserts) == 10, "each of the 10 picks is sent to the page exactly once"
    assert {(i["side"], i["slot"]) for i in inserts} == {(s, n) for s in (0, 1) for n in range(5)}
    my_side = tracker.my_side
    assert all(i["role"] for i in inserts if i["side"] == my_side), "allies carry their role"
    assert not any(i["role"] for i in inserts if i["side"] != my_side), "enemy roles are unknown"


def test_second_draft_matches_first():
    """Same tracker, two drafts back to back: draft 2 must not inherit draft 1's state."""
    events = load_events()
    second = [{**events[0], "eventType": "Create"}, *events[1:]]
    tracker = ChampSelect()
    _, first_payloads, _ = replay(events, tracker)
    _, second_payloads, second_phases = replay(second, tracker)
    assert second_payloads == first_payloads
    assert second_phases[0] is Phase.PLANNING


def test_polling_turns_snapshots_into_one_create_and_one_delete():
    """What the HTTP fallback would emit if it saw these snapshots, two drafts in a row."""
    snapshots = [e["data"] for e in load_events()]  # ends with None (not in champ select)
    stream = [None, *snapshots, *snapshots]
    events = [diff_sessions(a, b) for a, b in zip(stream, stream[1:])]
    types = [e.event_type for e in events if e]
    assert types.count("Create") == 2
    assert types.count("Delete") == 2
    assert types[0] == "Create" and types[-1] == "Delete"
