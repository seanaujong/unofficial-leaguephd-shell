import json

from leaguephd_shell.champselect import ChampSelect
from leaguephd_shell.lcu import _from_cmdline, _parse_event, diff_sessions, CHAMP_SELECT_TOPIC


def solo_session(bans_done=0, picks_done=0, local_cell=2):
    """A ranked solo/duo session: 10 bans in one group, then picks 1-2-2-2-2-1.

    Uses real champion IDs (bans 21-30, picks 11-20) because the live page looks
    every ID up in its champion table and errors on unknown ones.
    """
    bans = [
        {"type": "ban", "actorCellId": c, "championId": 21 + c, "completed": c < bans_done,
         "isInProgress": False, "isAllyAction": (c <= 4) == (local_cell <= 4)}
        for c in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    ]
    order = [0, 5, 6, 1, 2, 7, 8, 3, 4, 9]
    picks = [
        [{"type": "pick", "actorCellId": c, "championId": 11 + c, "completed": i < picks_done,
          "isInProgress": bans_done == 10 and i == picks_done, "isAllyAction": (c <= 4) == (local_cell <= 4)}]
        for i, c in enumerate(order)
    ]
    roles = ["top", "jungle", "middle", "bottom", "utility"]
    base = 0 if local_cell <= 4 else 5
    return {
        "hasSimultaneousPicks": False,
        "localPlayerCellId": local_cell,
        "myTeam": [{"cellId": base + i, "assignedPosition": r} for i, r in enumerate(roles)],
        "actions": [bans, *picks],
    }


def test_first_update_sets_side_and_draft_type():
    cs = ChampSelect()
    changed, delta = cs.update(solo_session())
    assert changed and cs.my_side == 0 and cs.draft_type == "solo"
    assert delta == {"mode": None, "insert_list": [], "to_pick_phase": False}


def test_red_side():
    cs = ChampSelect()
    cs.update(solo_session(local_cell=7))
    assert cs.my_side == 1


def test_bans_fill_slots_per_side():
    cs = ChampSelect()
    cs.update(solo_session())
    changed, delta = cs.update(solo_session(bans_done=10))
    assert changed and delta["mode"] == "ban"
    assert cs.bans == [21, 22, 23, 24, 25, 26, 27, 28, 29, 30]


def test_pick_phase_and_inserts_with_roles():
    cs = ChampSelect()
    _, delta = cs.update(solo_session(bans_done=9))
    assert delta["to_pick_phase"] is False
    _, delta = cs.update(solo_session(bans_done=10))
    assert delta["to_pick_phase"] is True  # last ban locked, first pick now in progress

    changed, delta = cs.update(solo_session(bans_done=10, picks_done=3))
    assert delta["insert_list"] == [
        {"side": 0, "slot": 0, "champion_id": 11, "role": "TOP"},
        {"side": 1, "slot": 0, "champion_id": 16, "role": None},  # enemy: role unknown
        {"side": 1, "slot": 1, "champion_id": 17, "role": None},
    ]
    # Re-sending the same snapshot reports nothing new.
    assert cs.update(solo_session(bans_done=10, picks_done=3)) == (
        False, {"mode": None, "insert_list": [], "to_pick_phase": False})


def test_goes_inactive_after_ten_picks_and_stays_inactive():
    cs = ChampSelect()
    cs.update(solo_session(bans_done=10, picks_done=10))
    assert cs.num_picked == 10 and not cs.active
    assert cs.update(solo_session(bans_done=10, picks_done=10))[0] is False


def test_blind_pick_is_ignored():
    cs = ChampSelect()
    session = solo_session() | {"hasSimultaneousPicks": True}
    assert cs.update(session)[0] is False and cs.draft_type is None


def test_payload_matches_page_contract():
    cs = ChampSelect()
    _, delta = cs.update(solo_session(bans_done=2))
    payload = cs.payload(delta)
    json.dumps(payload)  # must be serializable for runJavaScript
    assert {"my_side", "bans", "picks", "updated"} <= payload.keys()
    assert {"mode", "insert_list", "to_pick_phase"} == payload["updated"].keys()
    assert repr(cs)  # the original's __repr__ raised TypeError


def test_cmdline_credentials():
    creds = _from_cmdline(["LeagueClientUx.exe", "--app-port=54321", "--remoting-auth-token=abc"])
    assert creds.port == 54321 and creds.password == "abc"
    assert _from_cmdline(["LeagueClientUx.exe"]) is None


def test_parse_event():
    raw = json.dumps([8, CHAMP_SELECT_TOPIC, {"eventType": "Update", "data": {"x": 1}}])
    event = _parse_event(raw)
    assert event.event_type == "Update" and event.data == {"x": 1}
    assert _parse_event(json.dumps([8, "OnJsonApiEvent_other", {}])) is None


def test_phase_from_session():
    from leaguephd_shell.phases import Phase

    def with_timer(session, phase):
        return session | {"timer": {"phase": phase}}

    assert Phase.from_session(with_timer(solo_session(), "PLANNING")) is Phase.PLANNING
    assert Phase.from_session(with_timer(solo_session(bans_done=4), "BAN_PICK")) is Phase.BANNING
    assert Phase.from_session(with_timer(solo_session(bans_done=10), "BAN_PICK")) is Phase.PICKING
    assert Phase.from_session(with_timer(solo_session(bans_done=10, picks_done=10), "FINALIZATION")) is Phase.FINALIZATION
    assert Phase.from_session(with_timer(solo_session(), "GAME_STARTING")) is Phase.GAME_STARTING
    assert Phase.from_session(solo_session() | {"hasSimultaneousPicks": True}) is Phase.BLIND_PICK
    assert not Phase.IDLE.in_champ_select and Phase.BANNING.in_champ_select


def test_poll_diff_events():
    a = {"gameId": 1, "timer": 30}
    assert diff_sessions(None, None) is None
    assert diff_sessions(None, a).event_type == "Create"
    assert diff_sessions(a, dict(a)) is None
    assert diff_sessions(a, {"gameId": 1, "timer": 29}).event_type == "Update"
    assert diff_sessions(a, {"gameId": 2}).event_type == "Create"  # dodge/requeue
    assert diff_sessions(a, None).event_type == "Delete"
