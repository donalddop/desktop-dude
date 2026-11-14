"""Where the dude keeps his stuff: next to the code when run from source; as an app %LOCALAPPDATA%\\DesktopDude
(Windows) or ~/Library/Application Support/DesktopDude (macOS)."""

import os
import sys
from pathlib import Path


def _data_dir() -> Path:
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            d = Path.home() / "Library" / "Application Support" / "DesktopDude"
        else:
            d = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "DesktopDude"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).resolve().parent


DATA = _data_dir()
VERSION = "1.5.1"
