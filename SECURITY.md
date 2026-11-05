# Security policy

## Reporting a problem

Please report security problems privately, not in a public issue: use GitHub's
**Report a vulnerability** button on this repository's
[Security tab](https://github.com/seanaujong/unofficial-leaguephd-shell/security/advisories/new).

You'll get a reply within a week. Fixes ship as a new release, and the advisory
is published once a fixed release is out.

## Supported versions

Only the latest release gets fixes.

## Scope

In scope: this app's code, its build and release workflow, and the files it
ships (including bundled dependencies, which get updated when they have a fix).

Out of scope: leaguephd.com itself and the League client. Report those to
League PhD and to Riot Games respectively.

## What the app can access

See [What it does on your computer](README.md#what-it-does-on-your-computer).
In short: it reads the League client's local API password from the client's
process or lockfile, reads champ select from `127.0.0.1`, displays
leaguephd.com, and asks GitHub's API once at startup whether a newer release
exists (it only shows a link; it never downloads anything). It sends nothing to
the League client and stores nothing on disk.
