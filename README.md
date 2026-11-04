# leaguephd-shell

A modernized desktop shell for [League PhD](https://www.leaguephd.com): it reads your
live champ select from the League client and feeds it into leaguephd.com's
pick-now page, which returns pick suggestions.

A rewrite of [leaguephd/leaguephd-app](https://github.com/leaguephd/leaguephd-app)
(GPL-3.0) on Python 3.12 + PySide6, without the unmaintained `lcu-driver`.

## Run

```
uv run leaguephd-shell           # normal
uv run leaguephd-shell --debug   # verbose logs + records raw events to logs/session.jsonl
uv run leaguephd-shell --page-logs  # also show the site's JS console and Chromium network errors
uv run pytest                    # tests
```

Start it before or after the League client; it waits and reconnects on its own.

## How it works

| File | Role |
|---|---|
| `lcu.py` | Finds `LeagueClientUx.exe`, reads its port/password, streams `/lol-champ-select/v1/session` over the client's local WAMP websocket |
| `champselect.py` | Turns session snapshots into the `{my_side, bans, picks, updated}` object the page's `app_call()` expects |
| `window.py` | Qt window embedding the pick-now page; LCU asyncio loop runs on a background thread and talks to the UI via signals |

The recommendations come from leaguephd.com, not this app. If the site changes
its `app_call` contract, the window logs a warning.

## License

GPL-3.0-only. See [LICENSE](LICENSE).

This is a modified version of [leaguephd-app](https://github.com/leaguephd/leaguephd-app)
by leaguephd, also GPL-3.0. Changes (2026-11-04): rewritten for Python 3.12 and
PySide6; `lcu-driver` replaced with a built-in LCU client; `ChampSelect` ported
with bug fixes; the app reconnects instead of quitting when the League client closes.

This license covers this app's code only. The leaguephd.com website, its page
scripts and its recommendation service are not part of this project and are not
covered by it. Not endorsed by Riot Games or leaguephd.
