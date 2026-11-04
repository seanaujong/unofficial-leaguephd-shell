# SPDX-License-Identifier: GPL-3.0-only

"""Minimal client for the League Client Update (LCU) API.

The League client runs a local HTTPS + WAMP websocket server on 127.0.0.1.
Its port and password change every launch; we read them from the
LeagueClientUx.exe command line (or the install folder's ``lockfile``).

This replaces the unmaintained ``lcu-driver`` package with ~100 lines we own.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

import aiohttp
import psutil

from .phases import Phase

log = logging.getLogger(__name__)

CLIENT_PROCESS_NAMES = {"LeagueClientUx.exe", "LeagueClientUx"}
CHAMP_SELECT_URI = "/lol-champ-select/v1/session"
CHAMP_SELECT_TOPIC = "OnJsonApiEvent_lol-champ-select_v1_session"

# WAMP 1.0 message type codes used by the LCU websocket.
WAMP_SUBSCRIBE = 5
WAMP_EVENT = 8


@dataclass(frozen=True)
class Credentials:
    port: int
    password: str

    @property
    def base_url(self) -> str:
        return f"https://127.0.0.1:{self.port}"

    @property
    def headers(self) -> dict[str, str]:
        token = base64.b64encode(f"riot:{self.password}".encode()).decode()
        return {"Authorization": f"Basic {token}"}


@dataclass(frozen=True)
class SessionEvent:
    """A champ select session change. ``event_type`` is Create, Update or Delete."""

    event_type: str
    data: dict | None


def find_credentials() -> Credentials | None:
    """Return the running client's credentials, or None if it isn't running."""
    for proc in psutil.process_iter(["name", "cmdline", "exe"]):
        if proc.info["name"] not in CLIENT_PROCESS_NAMES:
            continue
        creds = _from_cmdline(proc.info["cmdline"] or [])
        if creds:
            return creds
        if proc.info["exe"]:
            creds = _from_lockfile(Path(proc.info["exe"]).parent / "lockfile")
            if creds:
                return creds
    return None


def _from_cmdline(args: list[str]) -> Credentials | None:
    values = {}
    for arg in args:
        if arg.startswith("--") and "=" in arg:
            key, _, value = arg[2:].partition("=")
            values[key] = value
    try:
        return Credentials(int(values["app-port"]), values["remoting-auth-token"])
    except (KeyError, ValueError):
        return None


def _from_lockfile(path: Path) -> Credentials | None:
    # Format: LeagueClient:<pid>:<port>:<password>:https
    try:
        _, _, port, password, _ = path.read_text().strip().split(":")
        return Credentials(int(port), password)
    except (OSError, ValueError):
        return None


async def champ_select_events(
    creds: Credentials, poll_seconds: float = 0.5
) -> AsyncIterator[SessionEvent]:
    """Yield the current champ select state, then every change, until the client closes.

    Tries the client's websocket first. Some client versions reject it (404 at
    "/"), so if the handshake fails we fall back to polling the session over
    HTTP, which every version supports.

    The client uses a self-signed certificate, so TLS verification is off. That's
    acceptable only because we talk exclusively to 127.0.0.1.
    """
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(
        base_url=creds.base_url, headers=creds.headers, connector=connector
    ) as http:
        # Connecting mid-champ-select: replay the current state first.
        async with http.get(CHAMP_SELECT_URI) as resp:
            current = await resp.json() if resp.status == 200 else None
        if current is not None:
            yield SessionEvent("Update", current)

        try:
            ws = await http.ws_connect("/", protocols=("wamp",), heartbeat=30)
        except aiohttp.WSServerHandshakeError as exc:
            log.info("LCU websocket unavailable (%s); polling instead", exc.status)
            async for event in _poll(http, current, poll_seconds):
                yield event
            return

        async with ws:
            await ws.send_str(json.dumps([WAMP_SUBSCRIBE, CHAMP_SELECT_TOPIC]))
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT or not msg.data:
                    continue
                event = _parse_event(msg.data)
                if event:
                    yield event


async def _poll(
    http: aiohttp.ClientSession, last: dict | None, interval: float
) -> AsyncIterator[SessionEvent]:
    """Turn repeated GETs into the same Create/Update/Delete events the websocket sends."""
    while True:
        await asyncio.sleep(interval)
        async with http.get(CHAMP_SELECT_URI) as resp:
            if resp.status == 200:
                session = await resp.json()
            elif resp.status == 404:  # not in champ select
                session = None
            else:
                resp.raise_for_status()
                continue
        event = diff_sessions(last, session)
        if event:
            yield event
        last = session


def diff_sessions(old: dict | None, new: dict | None) -> SessionEvent | None:
    if old is None and new is None:
        return None
    if old is None:
        return SessionEvent("Create", new)
    if new is None:
        return SessionEvent("Delete", None)
    # A new gameId means a new lobby's draft, even with no 404 in between.
    if new.get("gameId") != old.get("gameId"):
        return SessionEvent("Create", new)
    return SessionEvent("Update", new) if new != old else None


def _parse_event(raw: str) -> SessionEvent | None:
    try:
        code, topic, payload = json.loads(raw)
    except ValueError:
        return None
    if code != WAMP_EVENT or topic != CHAMP_SELECT_TOPIC:
        return None
    return SessionEvent(payload.get("eventType", ""), payload.get("data"))


async def run_forever(on_phase, on_event, poll_seconds: float = 2.0) -> None:
    """Wait for the client, stream events, and reconnect if it restarts.

    Drives the connection phases: WAITING_FOR_CLIENT until credentials are
    found, IDLE once connected. Champ select phases come from the events.
    Unlike the original app, closing the League client doesn't quit this app;
    it just goes back to waiting.
    """
    while True:
        creds = find_credentials()
        if creds is None:
            on_phase(Phase.WAITING_FOR_CLIENT)
            await asyncio.sleep(poll_seconds)
            continue
        try:
            on_phase(Phase.IDLE)
            async for event in champ_select_events(creds):
                on_event(event)
            log.info("LCU websocket closed")
        except aiohttp.ClientError as exc:
            # Common right after launch, before the API is listening.
            log.info("LCU connection failed: %s", exc)
        on_phase(Phase.WAITING_FOR_CLIENT)
        await asyncio.sleep(poll_seconds)
