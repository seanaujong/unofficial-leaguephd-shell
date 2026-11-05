# Unofficial League PhD

> **Unofficial.** Not made by or affiliated with [League PhD](https://www.leaguephd.com)
> or Riot Games. See [Disclaimers](#disclaimers).

A desktop app that reads your live champ select from the League client and feeds it
into leaguephd.com's pick-now page, which returns pick suggestions.

It's a rewrite of [leaguephd/leaguephd-app](https://github.com/leaguephd/leaguephd-app)
(GPL-3.0), the original League PhD desktop app, which stopped being updated. This
version runs on current Python and Qt and works with the current League client.

## Download

From [Releases](https://github.com/seanaujong/unofficial-leaguephd-shell/releases), pick one:

- **Installer (recommended):** `UnofficialLeaguePhd-Setup-v<version>.exe`. Installs
  for your user only (no admin rights), adds a Start menu shortcut, and can be
  removed from Windows Settings → Installed apps.
- **Portable:** `UnofficialLeaguePhd-v<version>-windows-x64.zip`. Unzip anywhere and
  run `UnofficialLeaguePhd.exe`; keep the folder together (the exe needs
  `_internal\` next to it). Delete the folder to remove it.

**Nothing else to install.** Python and every library the app needs are included.
You don't need Python, uv or anything from the "Run from source" section below.

The exe isn't code-signed yet (see [Code signing policy](#code-signing-policy)), so
Windows SmartScreen may warn on first run ("More info" → "Run anyway").

### Verify your download

Releases are built by GitHub Actions from the tagged commit, not on anyone's PC
(see [`.github/workflows/release.yml`](.github/workflows/release.yml)). Each release
has a GitHub build-provenance attestation, which proves the zip came from that
workflow run on this repository:

```
gh attestation verify <downloaded file> --repo seanaujong/unofficial-leaguephd-shell
```

Each release also lists every file's SHA-256 (and attaches `SHA256SUMS.txt`). To
check a download in PowerShell:

```
Get-FileHash .\<downloaded file> -Algorithm SHA256
```

## What it does on your computer

So you can judge whether it's safe to run:

- **Finds the League client** by looking for the `LeagueClientUx.exe` process and
  reading its command line (or the `lockfile` in its install folder) for the port
  and password of the client's local API. These change every time the client starts.
- **Reads champ select, nothing else.** It only reads `/lol-champ-select/v1/session`
  from the client on `127.0.0.1` (this machine). It never sends commands to the
  client, never picks or bans for you, and doesn't touch game memory or files.
- **Shows leaguephd.com** in an embedded browser (Qt WebEngine, which is Chromium)
  and passes your draft to that page. Links to other sites open in your normal browser.
- **Stores nothing.** The embedded browser runs off the record: no cookies or cache
  are saved to disk. The app writes no files, unless you run it from source with
  `--debug`, which records champ select events to `logs/session.jsonl`.
- **Checks for updates, once, at startup.** It asks GitHub's API whether this
  repository has a newer release and, if so, shows "Update available" in the
  status bar, linking to the release page. It never downloads or installs
  anything; updating is up to you. The request carries no personal data, only a
  User-Agent naming the app and version. To turn it off, start the app with
  `--no-update-check`.
- **Runs one copy at a time.** Starting it while it's already open brings the
  open window to the front instead (via a local named pipe; nothing leaves your PC).
- **No telemetry, no automatic updates, no admin rights**, and no other network
  connections than the three above.

The code that does each of these is short: [`lcu.py`](src/leaguephd_shell/lcu.py)
(the League client), [`window.py`](src/leaguephd_shell/window.py) (the page) and
[`updates.py`](src/leaguephd_shell/updates.py) (the update check).

### Updating

Download the new installer from Releases and run it: it replaces the old version
in place (same folder, shortcut and Installed apps entry) and closes the app first
if it's running. For the portable zip, replace the folder.

## Privacy

- Your **draft** (side, bans, picks and your team's roles, as champion IDs) is sent
  to leaguephd.com so it can make suggestions. No summoner names or account IDs
  are sent; the app doesn't pass them to the page.
- leaguephd.com is a website with its own **ads and analytics** (for example
  Google ad and analytics scripts), which run inside the app's window just as they
  would in your browser. What they collect is covered by leaguephd.com's own
  policies, not this project.
- The startup update check asks GitHub for this repository's latest release.
  Like any web request, GitHub sees your IP address; the request itself carries
  no personal data. Turn it off with `--no-update-check`.
- This project collects nothing itself.

## Code signing policy

Releases are **not yet signed**. The plan is to apply to
[SignPath Foundation](https://signpath.org) for free open-source code signing.
If accepted, signed releases will say so here and in the release notes.

- Committers and reviewers: [@seanaujong](https://github.com/seanaujong)
- Approvers (sign off each release): [@seanaujong](https://github.com/seanaujong)
- Only files built by this repository's release workflow are released.
- Privacy: see [Privacy](#privacy).

## Security

To report a security problem, see [SECURITY.md](SECURITY.md). Every push is
checked by CodeQL code scanning, and Dependabot proposes dependency updates.

## Run from source

For developers only; to just use the app, see [Download](#download). Needs
[uv](https://docs.astral.sh/uv/) on Windows.

```
uv run leaguephd-shell              # normal
uv run leaguephd-shell --debug      # verbose logs + records raw events to logs/session.jsonl
uv run leaguephd-shell --page-logs  # also show the site's JS console and Chromium network errors
uv run pytest                       # tests
```

Start it before or after the League client; it waits and reconnects on its own.

## Build the exe

```
uv run pyinstaller packaging/leaguephd.spec --noconfirm
```

Output is `dist/UnofficialLeaguePhd/UnofficialLeaguePhd.exe`, with a `licenses/`
folder holding every bundled component's licence (~410 MB, most of it Qt's
embedded Chromium).

To build the installer from that folder, with [Inno Setup 6](https://jrsoftware.org/isinfo.php):

```
ISCC /DAppVersion=<version> packaging\installer.iss
```

Output is `dist/UnofficialLeaguePhd-Setup-v<version>.exe` (~115 MB). When
testing an installer on a machine that also has the app installed for real, add
`/DAppIdGuid=00000000-0000-0000-0000-000000000001` so the test install and
uninstall can't replace or remove the real install's Installed apps entry. Releases
do all of this in GitHub Actions; see `.github/workflows/release.yml`.

## Test with a real draft, instantly

`tests/test_replay.py` replays a recorded ranked draft (92 events) through the
app's real `DraftController`, with a fake page in place of the browser, in well
under a second. It covers back-to-back drafts, slow page loads, browsing away
mid-draft, and a late "ready" from a page being replaced.
To add another recording, play a game with `--debug`, then scrub it, which
keeps only the fields the app reads and drops player names and IDs:

```
uv run python scripts/scrub_recording.py logs/session.jsonl tests/fixtures/<name>.jsonl
```

## How it works

| File | Role |
|---|---|
| `lcu.py` | Finds `LeagueClientUx.exe`, reads its port/password, and follows `/lol-champ-select/v1/session` (websocket, or HTTP polling when the client rejects the websocket) |
| `champselect.py` | Turns session snapshots into the `{my_side, bans, picks, updated}` object the page's `app_call()` expects |
| `controller.py` | All draft logic, no Qt: phases, when to reload the page, queueing updates until the page is ready |
| `window.py` | Thin Qt layer: embeds the pick-now page and carries out the controller's requests; the LCU asyncio loop runs on a background thread and talks to it via signals |
| `phases.py` | The app's phases (waiting → idle → planning → banning → picking → finalization → game starting); see [docs/phases.md](docs/phases.md) |

The recommendations come from leaguephd.com, not this app. If the site changes
its `app_call` contract, the window logs a warning.

## License

GPL-3.0-only. See [LICENSE](LICENSE). Bundled third-party components and their
licences are listed in [licenses/THIRD_PARTY_NOTICES.md](licenses/THIRD_PARTY_NOTICES.md).

This is a modified version of [leaguephd-app](https://github.com/leaguephd/leaguephd-app)
by leaguephd, also GPL-3.0. Changes (2026-11-04): rewritten for Python 3.12 and
PySide6; `lcu-driver` replaced with a built-in LCU client; `ChampSelect` ported
with bug fixes; the app reconnects instead of quitting when the League client closes.
The app icon is League PhD's logo, from leaguephd-app's assets, used to show which
site the app works with.

This licence covers this app's code only. The leaguephd.com website, its page
scripts and its recommendation service are not part of this project and are not
covered by it.

## Disclaimers

Unofficial League PhD is not made, endorsed or supported by League PhD
(leaguephd.com). "League PhD" and its logo belong to League PhD.

Unofficial League PhD isn't endorsed by Riot Games and doesn't reflect the views
or opinions of Riot Games or anyone officially involved in producing or managing
Riot Games properties. Riot Games, and all associated properties are trademarks
or registered trademarks of Riot Games, Inc.
