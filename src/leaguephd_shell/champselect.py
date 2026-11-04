# SPDX-License-Identifier: GPL-3.0-only
#
# Derived from ChampSelect.py in leaguephd-app by leaguephd
# (https://github.com/leaguephd/leaguephd-app), licensed under GPL-3.0.
# Modified 2026-11-04: restructured as a dataclass, fixed __repr__ raising
# TypeError, roles looked up by cellId, no re-activation after the draft ends.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3 as published by
# the Free Software Foundation. It is distributed WITHOUT ANY WARRANTY; see
# the LICENSE file for details.

"""Tracks a champ select draft and reports what changed on each LCU update.

Ported from leaguephd-app's ChampSelect.py. The output shape is the
contract the leaguephd.com pick-now page's ``app_call(obj)`` expects:

    {
      "my_side": 0 | 1,                      # 0 = blue, 1 = red
      "bans": [champion_id | None] * 10,     # 0-4 blue, 5-9 red
      "picks": [[{"champion_id", "role"}] * 5, [...] * 5],
      "updated": {
        "mode": "ban" | None,
        "insert_list": [{"side", "slot", "champion_id", "role"}],
        "to_pick_phase": bool,
      },
      ...plus the tracker's other state fields
    }
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

ROLE_LABELS = {
    "top": "TOP",
    "jungle": "JGL",
    "middle": "MID",
    "bottom": "ADC",
    "utility": "SUP",
}

BLUE, RED = 0, 1


def _side_of(cell_id: int) -> int:
    # Cells 0-4 are blue side, 5-9 red side.
    return BLUE if cell_id <= 4 else RED


def _empty_picks() -> list[list[dict]]:
    return [[{"champion_id": None, "role": None} for _ in range(5)] for _ in range(2)]


@dataclass
class ChampSelect:
    active: bool = False
    draft_type: str | None = None  # "solo" (10 bans up front) or "tournament"
    my_side: int | None = None
    num_banned: int = 0
    bans: list[int | None] = field(default_factory=lambda: [None] * 10)
    num_picked: int = 0
    picks: list[list[dict]] = field(default_factory=_empty_picks)
    has_pick_started: bool = False

    def reset(self) -> None:
        self.__init__()

    def update(self, session: dict) -> tuple[bool, dict]:
        """Apply an LCU session snapshot. Returns (changed, what_changed)."""
        changed = False
        delta = {"mode": None, "insert_list": [], "to_pick_phase": False}
        action_groups = session.get("actions") or []

        if self.draft_type is None:
            # Blind pick (simultaneous picks) has no draft to analyse.
            if session.get("hasSimultaneousPicks"):
                return False, delta
            self.active = True
            first = action_groups[0] if action_groups else []
            self.draft_type = "solo" if len(first) == 10 else "tournament"
        if not self.active:  # all 10 picks are in; nothing more to report
            return False, delta

        if self.my_side is None:
            self.my_side = _side_of(session["localPlayerCellId"])
            changed = True

        actions = [a for group in action_groups for a in group]
        bans = [a for a in actions if a.get("type") == "ban"]
        picks = [a for a in actions if a.get("type") == "pick"]

        if self._update_bans(bans):
            changed = True
            delta["mode"] = "ban"

        if not self.has_pick_started and any(
            p.get("completed") or p.get("isInProgress") for p in picks
        ):
            self.has_pick_started = True
            delta["to_pick_phase"] = True
            changed = True

        if self.has_pick_started:
            inserted = self._update_picks(picks, session.get("myTeam") or [])
            if inserted:
                delta["insert_list"] = inserted
                changed = True

        return changed, delta

    def _update_bans(self, bans: list[dict]) -> bool:
        # Ban slots fill in order per side, not by cell ID, so count ban
        # actions per side (completed or not) to find each one's slot.
        next_slot = {BLUE: 0, RED: 5}
        new_bans = list(self.bans)
        count = 0
        for ban in bans:
            side = _side_of(ban["actorCellId"])
            slot = next_slot[side]
            next_slot[side] += 1
            if ban.get("completed") and slot < 10:
                new_bans[slot] = ban.get("championId")
                count += 1
        if count > self.num_banned:
            self.bans = new_bans
            self.num_banned = count
            return True
        return False

    def _update_picks(self, picks: list[dict], my_team: list[dict]) -> list[dict]:
        roles_by_cell = {
            m.get("cellId"): ROLE_LABELS.get(m.get("assignedPosition", ""))
            for m in my_team
        }
        inserted = []
        for pick in picks:
            if not pick.get("completed"):
                continue
            cell = pick["actorCellId"]
            side = _side_of(cell)
            slot = cell if side == BLUE else cell - 5
            if self.picks[side][slot]["champion_id"] is not None:
                continue
            role = roles_by_cell.get(cell) if pick.get("isAllyAction") else None
            self.picks[side][slot] = {"champion_id": pick.get("championId"), "role": role}
            inserted.append(
                {"side": side, "slot": slot, "champion_id": pick.get("championId"), "role": role}
            )
        self.num_picked += len(inserted)
        if self.num_picked > 9:
            self.active = False
        return inserted

    def payload(self, delta: dict) -> dict:
        """The object to hand to the page's ``app_call``."""
        return {**asdict(self), "updated": delta}
