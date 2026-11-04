# SPDX-License-Identifier: GPL-3.0-only
"""Turn a --debug recording (logs/session.jsonl) into a shareable test fixture.

Keeps only the fields the app reads, which drops every player's name, tag,
PUUID and summoner ID, plus chat details. The gameId is replaced with a fake one.

    uv run python scripts/scrub_recording.py logs/session.jsonl tests/fixtures/ranked_draft.jsonl
"""

import json
import sys

FAKE_GAME_ID = 1


def scrub_member(m: dict) -> dict:
    return {k: m.get(k) for k in ("cellId", "assignedPosition", "championId")}


def scrub_session(s: dict | None) -> dict | None:
    if s is None:
        return None
    return {
        "gameId": FAKE_GAME_ID,
        "hasSimultaneousPicks": s.get("hasSimultaneousPicks"),
        "localPlayerCellId": s.get("localPlayerCellId"),
        "timer": {"phase": (s.get("timer") or {}).get("phase")},
        "myTeam": [scrub_member(m) for m in s.get("myTeam") or []],
        "theirTeam": [scrub_member(m) for m in s.get("theirTeam") or []],
        "actions": [
            [{k: a.get(k) for k in ("actorCellId", "championId", "completed", "isAllyAction", "isInProgress", "type")}
             for a in group]
            for group in s.get("actions") or []
        ],
    }


def main(src: str, dst: str) -> None:
    with open(src, encoding="utf-8") as fin, open(dst, "w", encoding="utf-8", newline="\n") as fout:
        for line in fin:
            event = json.loads(line)
            event["data"] = scrub_session(event["data"])
            fout.write(json.dumps(event, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:3])
