# SPDX-License-Identifier: GPL-3.0-only

"""Tell the user when a newer release exists. Never downloads or installs anything.

One request at startup to GitHub's "latest release" API, which ignores drafts
and pre-releases. It sends no personal data: just a generic User-Agent naming
this app and its version, which GitHub's API requires. Failures are silent.
Turn it off with --no-update-check.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger(__name__)

REPO = "seanaujong/unofficial-leaguephd-shell"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"


@dataclass(frozen=True)
class Update:
    version: str  # e.g. "0.1.2"
    url: str  # release page to open in the browser


def parse_version(text: str) -> tuple[int, int, int] | None:
    """'v0.1.2' or '0.1.2' -> (0, 1, 2). None for anything else (e.g. '1.0-rc1')."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", text.strip())
    return tuple(int(x) for x in m.groups()) if m else None


def newer_release(current: str, release: dict) -> Update | None:
    """The update to offer, given GitHub's latest-release JSON, or None."""
    if release.get("draft") or release.get("prerelease"):
        return None
    latest, mine = parse_version(release.get("tag_name", "")), parse_version(current)
    if latest is None or mine is None or latest <= mine:
        return None
    url = release.get("html_url", "")
    if not url.startswith(f"https://github.com/{REPO}/releases/"):
        url = RELEASES_PAGE  # only ever link to this repo's releases
    return Update(".".join(map(str, latest)), url)


def fetch_latest_release(current: str, timeout: float = 5.0) -> dict:
    request = urllib.request.Request(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"unofficial-leaguephd-shell/{current}",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def check_for_update(
    current: str, fetch: Callable[[str], dict] = fetch_latest_release
) -> Update | None:
    """Ask GitHub; return an Update if a newer release exists. Never raises."""
    try:
        return newer_release(current, fetch(current))
    except Exception as exc:  # offline, rate-limited, no releases yet (404)...
        log.debug("update check failed: %s", exc)
        return None
