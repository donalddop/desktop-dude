"""Auto-update from GitHub releases.

Every few hours (and on demand from the tray) it asks GitHub for the latest release. If that is newer,
the installed exe downloads DesktopDude-setup.exe, checks its SHA-256 against the digest GitHub publishes,
runs it silently and quits; the installer starts the new version. The portable zip only gets a
notification, and running from source never updates anything.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

from appdir import DATA, VERSION
from terror import _log

REPO = "donalddop/desktop-dude"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES = f"https://github.com/{REPO}/releases/latest"
FIRST_CHECK, EVERY = 60.0, 6 * 3600.0


def parse(v: str) -> tuple:
    nums = [int(x) for x in re.findall(r"\d+", v)[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def _get(url, accept="application/vnd.github+json"):
    req = urllib.request.Request(url, headers={"User-Agent": "DesktopDude-updater", "Accept": accept})
    return urllib.request.urlopen(req, timeout=30)


class Updater:
    def __init__(self, real: bool):
        fake = os.environ.get("DUDE_FAKE_VERSION")  # test hook: pretend to be an older installed build
        self.version = fake or VERSION
        frozen = bool(getattr(sys, "frozen", False))
        self.active = real and frozen
        self.installed = bool(fake) or (frozen and "\\programs\\desktopdude\\" in sys.executable.lower())
        self.path = DATA / "update.json"
        self.auto = True
        if real and self.path.exists():
            try:
                self.auto = bool(json.loads(self.path.read_text(encoding="utf-8")).get("auto", True))
            except (OSError, ValueError):
                pass
        self.next, self.busy, self.result = FIRST_CHECK, False, None
        self.fetch_json = lambda: json.loads(_get(API).read())
        self.download = self._download
        self.spawn = lambda fn: threading.Thread(target=fn, daemon=True).start()

    def set_auto(self, on: bool):
        self.auto = on
        try:
            self.path.write_text(json.dumps({"auto": on}), encoding="utf-8")
        except OSError as e:
            _log(f"update setting not saved: {e!r}")

    def step(self, t) -> tuple | None:
        """Main thread, every frame. Returns a finished result once: (kind, version, extra)."""
        if self.result is not None:
            r, self.result = self.result, None
            return r
        if self.active and self.auto and not self.busy and t >= self.next:
            self.next = t + EVERY
            self.check(manual=False)
        return None

    def check(self, manual=True):
        if self.busy:
            return
        self.busy = True
        self.spawn(lambda: self._check(manual))

    def _check(self, manual):
        try:
            rel = self.fetch_json()
            latest = rel["tag_name"]
            if parse(latest) <= parse(self.version):
                self.result = ("uptodate", latest, None) if manual else None
                return
            asset = next(a for a in rel["assets"] if a["name"].lower().endswith("-setup.exe"))
            if not self.installed:
                self.result = ("available", latest, rel.get("html_url", RELEASES))
                return
            path = Path(tempfile.gettempdir()) / f"DesktopDude-{latest}-setup.exe"
            sha = self.download(asset["browser_download_url"], path)
            digest = asset.get("digest") or ""
            if digest.startswith("sha256:") and digest[7:].lower() != sha:
                path.unlink(missing_ok=True)
                raise ValueError(f"checksum mismatch for {asset['name']}")
            self.result = ("install", latest, path)
        except Exception as e:  # noqa: BLE001 - offline, rate limited, no setup asset: try again later
            _log(f"update check failed: {e!r}")
            self.result = ("error", "", str(e)) if manual else None
        finally:
            self.busy = False

    @staticmethod
    def _download(url, path: Path) -> str:
        h = hashlib.sha256()
        tmp = path.with_suffix(".part")
        with _get(url, "application/octet-stream") as r, open(tmp, "wb") as f:
            while chunk := r.read(1 << 16):
                h.update(chunk)
                f.write(chunk)
        tmp.replace(path)
        return h.hexdigest()

    @staticmethod
    def run_installer(path: Path):
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([str(path), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                         creationflags=flags, close_fds=True)
