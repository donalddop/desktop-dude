"""The game-feel numbers moved out of terror.py/warfare.py into tuning.py: defaults must not drift."""

import json

import tuning
from tuning import Tuning, from_dict, load


def test_defaults_match_the_old_hardcoded_numbers():
    t = Tuning()
    assert (t.rage_angry, t.rage_blackout) == (0.4, 0.7)
    assert (t.rage_drones, t.rage_drones_three, t.rage_tank, t.rage_air) == (0.45, 0.8, 0.65, 0.85)
    assert (t.terror_first_delay_s, t.terror_every_calm_s, t.terror_every_angry_s) == (25.0, 45.0, 12.0)
    assert t.terror_cooldown_calm_s == (30.0, 60.0)
    assert t.terror_cooldown_angry_s == (10.0, 20.0)
    assert t.blackout_cooldown_s == 120.0
    assert t.terror_weights == {
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
    assert (t.drones_rate, t.tank_rate, t.air_rate) == (0.5, 0.35, 0.35)
    assert (t.drones_first_s, t.tank_first_s, t.air_first_s) == (6.0, 12.0, 20.0)
    assert (t.drones_cooldown_s, t.tank_cooldown_s, t.air_cooldown_s) == (45.0, 75.0, 60.0)


def test_weights_are_not_shared_between_instances():
    a, b = Tuning(), Tuning()
    a.terror_weights["popup"] = 99
    assert b.terror_weights["popup"] == 1.5


def test_overrides_change_only_what_is_given():
    t = from_dict(
        {
            "terror_every_calm_s": 90,
            "rage_tank": 0.75,
            "terror_weights": {"popup": 0.5},
            "terror_cooldown_angry_s": [25, 15],
        }
    )
    assert t.terror_every_calm_s == 90.0 and t.rage_tank == 0.75
    assert t.terror_weights["popup"] == 0.5 and t.terror_weights["graffiti"] == 3.0
    assert t.terror_cooldown_angry_s == (15.0, 25.0)
    assert t.terror_every_angry_s == 12.0


def test_bad_values_are_skipped_and_logged():
    said = []
    t = from_dict(
        {
            "nope": 1,
            "rage_air": "hoog",
            "tank_rate": -1,
            "blackout_cooldown_s": True,
            "terror_weights": {"nuke": 5, "taunt": "x"},
            "terror_cooldown_calm_s": [1],
        },
        said.append,
    )
    assert t == Tuning()
    assert len(said) == 7


def test_load_reads_the_tuning_block_from_dude_config(tmp_path):
    p = tmp_path / "dude_config.json"
    p.write_text("﻿" + json.dumps({"lat": 52.2, "tuning": {"air_cooldown_s": 120}}), encoding="utf-8")
    assert load(p).air_cooldown_s == 120.0


def test_load_falls_back_to_defaults(tmp_path):
    assert load(tmp_path / "missing.json") == Tuning()
    bad = tmp_path / "dude_config.json"
    bad.write_text("{kapot", encoding="utf-8")
    said = []
    assert load(bad, said.append) == Tuning()
    assert said
    nob = tmp_path / "other.json"
    nob.write_text(json.dumps({"lat": 1}), encoding="utf-8")
    assert load(nob) == Tuning()


def test_current_is_read_once(monkeypatch):
    monkeypatch.setattr(tuning, "_current", None)
    first = tuning.current()
    assert tuning.current() is first


def test_rage_defaults_match_the_old_hardcoded_numbers():
    t = Tuning()
    assert t.rage_cooldown_per_s == 0.012
    assert (t.rage_punch, t.rage_throw, t.rage_throw_speed_bonus) == (0.12, 0.15, 0.2)
    assert (t.rage_parry, t.rage_rocket_jump) == (0.05, 0.1)


def test_reload_reads_dude_config_again(monkeypatch, tmp_path):
    import appdir

    monkeypatch.setattr(appdir, "DATA", tmp_path)
    monkeypatch.setattr(tuning, "_current", None)
    cfg = tmp_path / "dude_config.json"
    cfg.write_text(json.dumps({"tuning": {"rage_punch": 0.3}}), encoding="utf-8")
    first = tuning.current()
    assert first.rage_punch == 0.3
    cfg.write_text(json.dumps({"tuning": {"rage_punch": 0.5}}), encoding="utf-8")
    assert tuning.current() is first  # cached until a reload
    again = tuning.reload()
    assert again.rage_punch == 0.5
    assert tuning.current() is again
    monkeypatch.setattr(tuning, "_current", None)
