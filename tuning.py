"""How often and how hard the dude's rage, war and terror hit - every game-feel number in one place.

The defaults are exactly what terror.py and warfare.py used to have hardcoded. To tune them yourself, add a
"tuning" block to dude_config.json (next to the code, or %LOCALAPPDATA%\\DesktopDude for the exe) with only
the keys you want to change, e.g.:

    {"tuning": {"terror_every_calm_s": 90, "rage_tank": 0.75, "terror_weights": {"popup": 0.5}}}

Pick it up with "Reload tuning" in the tray menu (or restart the dude). Unknown keys and non-numbers are skipped (and logged), so a typo never
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

    # ---- rage: how fast he cools down and how much each hit adds (desktop_dude.py)
    rage_cooldown_per_s: float = 0.012  # rage drops this much per second
    rage_punch: float = 0.12  # you punch him
    rage_throw: float = 0.15  # you throw him ...
    rage_throw_speed_bonus: float = 0.2  # ... plus up to this much for a full-speed throw
    rage_parry: float = 0.05  # he blocks your punch with the katana
    rage_rocket_jump: float = 0.1  # his own rocket blows up next to him

    # ---- how rage drives his moves (desktop_dude.py): value = base + per_rage x rage, cooldowns floored
    chase_speed: float = 250.0  # px/s running after your cursor ...
    chase_speed_per_rage: float = 150.0  # ... plus this much at full rage
    climb_speed: float = 240.0  # px/s up a window edge ...
    climb_speed_per_rage: float = 140.0  # ... plus this much at full rage
    katana_cooldown_s: float = 4.5  # wait between katana slashes ...
    katana_cooldown_per_rage: float = 3.0  # ... minus this much at full rage ...
    katana_cooldown_min_s: float = 1.5  # ... but never shorter than this
    bazooka_cooldown_s: float = 8.0  # wait between bazooka shots ...
    bazooka_cooldown_per_rage: float = 4.0  # ... minus this much at full rage ...
    bazooka_cooldown_min_s: float = 3.0  # ... but never shorter than this
    slash_push: float = 160.0  # px a katana hit shoves your cursor ...
    slash_push_per_rage: float = 140.0  # ... plus this much at full rage
    grab_chance: float = 0.3  # chance he grabs your cursor when in reach ...
    grab_chance_per_rage: float = 0.3  # ... plus this much at full rage
    rocket_speed: float = 900.0  # px/s of a bazooka rocket ...
    rocket_speed_per_rage: float = 400.0  # ... plus this much at full rage
    rage_katana: float = 0.2  # from this rage he slashes with the katana
    rage_bazooka: float = 0.3  # from this rage he pulls the bazooka
    rage_chase_after_taunt: float = 0.3  # after a taunt he runs after you (instead of idling) above this rage
    rage_getup_notice: float = 0.35  # getting up after a throw: above this rage he spots you ('!')
    rage_kick: float = 0.3  # from this rage he kicks the window he stands on / bumps into ...
    kick_chance_per_rage_s: float = 0.3  # ... with this chance per second x rage
    rage_window_katana: float = 0.5  # above this rage a window attack may be a katana slash, not a kick ...
    window_katana_chance: float = 0.5  # ... with this chance (when the katana is ready)
    rage_parry_anytime: float = 0.3  # from this rage he can parry your punch outside a slash ...
    parry_chance: float = 0.35  # ... with this chance (mid-slash he always parries)
    attack_pause_s: float = 2.8  # pause after a kick/slash on a window ...
    attack_pause_per_rage: float = 1.8  # ... minus this much at full rage ...
    attack_pause_min_s: float = 0.8  # ... but never shorter than this

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

    def chase(self, rage: float) -> float:
        return self.chase_speed + self.chase_speed_per_rage * rage

    def climb(self, rage: float) -> float:
        return self.climb_speed + self.climb_speed_per_rage * rage

    def katana_cooldown(self, rage: float) -> float:
        return max(self.katana_cooldown_min_s, self.katana_cooldown_s - self.katana_cooldown_per_rage * rage)

    def slash(self, rage: float) -> float:
        return self.slash_push + self.slash_push_per_rage * rage

    def grab(self, rage: float) -> float:
        return self.grab_chance + self.grab_chance_per_rage * rage

    def rocket(self, rage: float) -> float:
        return self.rocket_speed + self.rocket_speed_per_rage * rage

    def kick_chance(self, rage: float, dt: float) -> float:
        return self.kick_chance_per_rage_s * rage * dt

    def attack_pause(self, rage: float) -> float:
        return max(self.attack_pause_min_s, self.attack_pause_s - self.attack_pause_per_rage * rage)

    def bazooka_cooldown(self, rage: float) -> float:
        return max(
            self.bazooka_cooldown_min_s, self.bazooka_cooldown_s - self.bazooka_cooldown_per_rage * rage
        )


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


def reload() -> Tuning:
    """Forget the cached tuning and read dude_config.json again (tray menu: Reload tuning)."""
    global _current
    _current = None
    return current()
