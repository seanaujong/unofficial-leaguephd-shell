# SPDX-License-Identifier: GPL-3.0-only

"""The app's phases: one explicit state for where you are, from launch to game start.

    WAITING_FOR_CLIENT ──client found──▶ IDLE ──champ select opens──▶ PLANNING
          ▲                               ▲                             │
          └──────client closes────────────┤                             ▼
                                          │                          BANNING
                                          │                             │
                                          │                             ▼
                                          │                          PICKING
                                          │                             │
                                          │                             ▼
                                          │                       FINALIZATION
                                          │                             │
                                          │                             ▼
                                          └──champ select closes── GAME_STARTING

Any champ select phase can jump back to IDLE (a dodge) or to WAITING_FOR_CLIENT
(the client closes). Blind pick goes to BLIND_PICK instead, which the page
can't analyse. See docs/phases.md for what each phase does.

The League client decides the phase; this module only names it. Connection
phases come from lcu.run_forever, and champ select phases are read from each
session snapshot with ``Phase.from_session``.
"""

from __future__ import annotations

from enum import Enum


class Phase(Enum):
    # Connection phases (set by lcu.run_forever)
    WAITING_FOR_CLIENT = "Waiting for the League client..."
    IDLE = "Connected to the League client"

    # Champ select phases (read from the session snapshot)
    PLANNING = "Champ select: declaring intent"
    BANNING = "Champ select: banning"
    PICKING = "Champ select: picking"
    FINALIZATION = "Champ select: finalizing loadouts"
    GAME_STARTING = "Game starting"
    BLIND_PICK = "Blind pick: no draft to analyse"

    @property
    def label(self) -> str:
        return self.value

    @property
    def in_champ_select(self) -> bool:
        return self not in (Phase.WAITING_FOR_CLIENT, Phase.IDLE)

    @classmethod
    def from_session(cls, session: dict) -> Phase:
        """Name the phase of an LCU champ select session snapshot.

        The client's ``timer.phase`` is PLANNING, BAN_PICK, FINALIZATION or
        GAME_STARTING. BAN_PICK covers both bans and picks, so we split it
        by whether any pick action has started.
        """
        if session.get("hasSimultaneousPicks"):
            return cls.BLIND_PICK
        lcu_phase = (session.get("timer") or {}).get("phase")
        if lcu_phase == "PLANNING":
            return cls.PLANNING
        if lcu_phase == "FINALIZATION":
            return cls.FINALIZATION
        if lcu_phase == "GAME_STARTING":
            return cls.GAME_STARTING
        picks_started = any(
            action.get("type") == "pick" and (action.get("completed") or action.get("isInProgress"))
            for group in session.get("actions") or []
            for action in group
        )
        return cls.PICKING if picks_started else cls.BANNING
