import hashlib

import updater
from updater import Updater, parse


def _upd(version="1.0", installed=True, digest=True, latest="v1.1"):
    u = Updater(real=False)
    u.version, u.installed = version, installed
    data = b"fake setup"
    sha = hashlib.sha256(data).hexdigest()
    asset = {"name": "DesktopDude-setup.exe", "browser_download_url": "https://x/setup.exe"}
    if digest:
        asset["digest"] = "sha256:" + (sha if digest is True else digest)
    u.fetch_json = lambda: {"tag_name": latest, "html_url": "https://rel", "assets": [
        {"name": "DesktopDude-standalone.zip", "browser_download_url": "https://x/zip"}, asset]}
    u.downloaded = []

    def download(url, path):
        u.downloaded.append((url, path))
        return sha

    u.download = download
    u.spawn = lambda fn: fn()
    return u


def test_parse_versions():
    assert parse("v1.1") == (1, 1, 0) and parse("2.10") > parse("2.9") > parse("v2.8.3")


def test_newer_release_gets_installed():
    u = _upd()
    u.check(manual=False)
    kind, ver, path = u.step(0)
    assert kind == "install" and ver == "v1.1" and u.downloaded[0][0] == "https://x/setup.exe"
    assert str(path).endswith("DesktopDude-v1.1-setup.exe")


def test_bad_checksum_is_refused():
    u = _upd(digest="00" * 32)
    u.check(manual=True)
    assert u.step(0)[0] == "error"


def test_up_to_date_is_quiet_unless_asked():
    u = _upd(version="1.1")
    u.check(manual=False)
    assert u.step(0) is None
    u.check(manual=True)
    assert u.step(0) == ("uptodate", "v1.1", None)


def test_portable_only_gets_a_link():
    u = _upd(installed=False)
    u.check(manual=False)
    assert u.step(0) == ("available", "v1.1", "https://rel") and not u.downloaded


def test_offline_fails_silently():
    u = _upd()

    def boom():
        raise OSError("offline")

    u.fetch_json = boom
    u.check(manual=False)
    assert u.step(0) is None and not u.busy


def test_never_checks_from_source():
    u = Updater(real=True)
    assert not u.active  # not frozen
    calls = []
    u.check = lambda manual=True: calls.append(manual)
    for t in (0, 100, 30000):
        u.step(t)
    assert not calls and updater.FIRST_CHECK == 60.0
