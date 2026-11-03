"""How often and how hard the dude's rage, war and terror hit - every game-feel number in one place.

The defaults are exactly what terror.py and warfare.py used to have hardcoded. To tune them yourself, add a
"tuning" block to dude_config.json (next to the code, or %LOCALAPPDATA%\\DesktopDude for the exe) with only
the keys you want to change, e.g.:

    {"tuning": {"terror_every_calm_s": 90, "rage_tank": 0.75, "terror_weights": {"popup": 0.5}}}

Restart the dude to pick it up. Unknown keys and non-numbers are skipped (and logged), so a typo never
breaks him.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields, replace
from pathlib import Path


def _weights() -> dict[str, float]:
    return {
        "graffiti": 3.0,
        "popup": 1.5,
        "taunt": 1.0,
        "steal": 2.0,
        "surf": 2.5,
        "hunt": 2.0,
        "glass": 2.5,
        "quake": 1.5,
        "blackout": 1.2,
    }


@dataclass(frozen=True)
class Tuning:
    # ---- rage thresholds (rage runs 0..1)
    rage_angry: float = 0.4  # from here terror gets angry: more often, plus glass and quake
    rage_blackout: float = 0.7  # from here a blackout (power cut) is possible
    rage_drones: float = 0.45  # war: drones
    rage_drones_three: float = 0.8  # war: three drones instead of two
    rage_tank: float = 0.65  # war: tank
    rage_air: float = 0.85  # war: airstrike

    # ---- terror: how often (on average one act per N seconds while idle) and the pause after one
    terror_first_delay_s: float = 25.0
    terror_every_calm_s: float = 45.0
    terror_every_angry_s: float = 12.0
    terror_cooldown_calm_s: tuple[float, float] = (30.0, 60.0)
    terror_cooldown_angry_s: tuple[float, float] = (10.0, 20.0)
    blackout_cooldown_s: float = 120.0
    terror_weights: dict[str, float] = field(default_factory=_weights)  # relative odds per act

    # ---- war: chance per second once rage is high enough, and the wait before the next one
    drones_rate: float = 0.5
    tank_rate: float = 0.35
    air_rate: float = 0.35
    drones_first_s: float = 6.0
    tank_first_s: float = 12.0
    air_first_s: float = 20.0
    drones_cooldown_s: float = 45.0
    tank_cooldown_s: float = 75.0
    air_cooldown_s: float = 60.0


def _number(v) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool) and v >= 0


def from_dict(raw: dict, log=lambda msg: None) -> Tuning:
    """Defaults with whatever valid overrides `raw` holds; anything odd is skipped and logged."""
    base = Tuning()
    known = {f.name for f in fields(Tuning)}
    changes: dict = {}
    for key, value in (raw or {}).items():
        if key not in known:
            log(f"tuning: unknown key {key!r} skipped")
            continue
        current = getattr(base, key)
        if isinstance(current, dict):
            if not isinstance(value, dict):
                log(f"tuning: {key} must be an object, skipped")
                continue
            merged = dict(current)
            for k, w in value.items():
                if k in merged and _number(w):
                    merged[k] = float(w)
                else:
                    log(f"tuning: {key}.{k} skipped")
            changes[key] = merged
        elif isinstance(current, tuple):
            if isinstance(value, list | tuple) and len(value) == 2 and all(map(_number, value)):
                lo, hi = sorted(float(v) for v in value)
                changes[key] = (lo, hi)
            else:
                log(f"tuning: {key} must be [min, max], skipped")
        elif _number(value):
            changes[key] = float(value)
        else:
            log(f"tuning: {key} must be a number >= 0, skipped")
    return replace(base, **changes)


def load(path: Path, log=lambda msg: None) -> Tuning:
    """The "tuning" block of dude_config.json, or the defaults if there is none or it can't be read."""
    try:
        if not path.exists():
            return Tuning()
        cfg = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        log(f"tuning: {path.name} unreadable ({e!r}), using defaults")
        return Tuning()
    raw = cfg.get("tuning") if isinstance(cfg, dict) else None
    return from_dict(raw if isinstance(raw, dict) else {}, log)


_current: Tuning | None = None


def current() -> Tuning:
    """The tuning the running dude uses: read once from dude_config.json, problems go to desktop_dude.log."""
    global _current
    if _current is None:
        import time

        from appdir import DATA

        def log(msg):
            try:
                with (DATA / "desktop_dude.log").open("a", encoding="utf-8") as f:
                    f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
            except OSError:
                pass

        _current = load(DATA / "dude_config.json", log)
    return _current
