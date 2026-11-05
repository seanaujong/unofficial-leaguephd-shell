from leaguephd_shell.updates import RELEASES_PAGE, check_for_update, newer_release, parse_version

RELEASE = "https://github.com/seanaujong/unofficial-leaguephd-shell/releases/tag/v0.2.0"


def release(tag, **extra):
    return {"tag_name": tag, "html_url": RELEASE, "draft": False, "prerelease": False, **extra}


def test_parse_version():
    assert parse_version("v0.1.2") == (0, 1, 2)
    assert parse_version("1.10.0") == (1, 10, 0)
    assert parse_version("v1.0-rc1") is None
    assert parse_version("") is None


def test_offers_only_strictly_newer_versions():
    assert newer_release("0.1.1", release("v0.2.0")).version == "0.2.0"
    assert newer_release("0.1.1", release("v0.1.10")).version == "0.1.10"  # numeric, not text
    assert newer_release("0.1.1", release("v0.1.1")) is None
    assert newer_release("0.2.0", release("v0.1.9")) is None


def test_ignores_drafts_prereleases_and_odd_tags():
    assert newer_release("0.1.1", release("v0.2.0", draft=True)) is None
    assert newer_release("0.1.1", release("v0.2.0", prerelease=True)) is None
    assert newer_release("0.1.1", release("nightly")) is None


def test_only_links_to_this_repos_releases():
    assert newer_release("0.1.1", release("v0.2.0")).url == RELEASE
    evil = release("v0.2.0", html_url="https://example.com/malware.exe")
    assert newer_release("0.1.1", evil).url == RELEASES_PAGE


def test_check_never_raises():
    def offline(_):
        raise OSError("no network")

    assert check_for_update("0.1.1", fetch=offline) is None
    assert check_for_update("0.1.1", fetch=lambda _: {"message": "Not Found"}) is None
    assert check_for_update("0.1.1", fetch=lambda _: release("v0.2.0")).version == "0.2.0"
