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


def test_move_numbers_match_the_old_hardcoded_formulas():
    t = Tuning()
    for rage in (0.0, 0.2, 0.5, 0.75, 1.0):
        assert t.chase(rage) == 250 + 150 * rage
        assert t.climb(rage) == 240 + 140 * rage
        assert t.katana_cooldown(rage) == max(1.5, 4.5 - 3 * rage)
        assert t.bazooka_cooldown(rage) == max(3.0, 8.0 - 4.0 * rage)


def test_move_numbers_can_be_overridden():
    t = from_dict({"chase_speed": 300, "katana_cooldown_min_s": 2.5, "bazooka_cooldown_per_rage": 6})
    assert t.chase(0.0) == 300.0 and t.chase(1.0) == 450.0
    assert t.katana_cooldown(1.0) == 2.5
    assert t.bazooka_cooldown(0.5) == 5.0 and t.bazooka_cooldown(1.0) == 3.0


def test_attack_numbers_match_the_old_hardcoded_formulas():
    t = Tuning()
    for rage in (0.0, 0.2, 0.5, 0.75, 1.0):
        assert t.slash(rage) == 160 + 140 * rage
        assert t.grab(rage) == 0.3 + 0.3 * rage
        assert t.rocket(rage) == 900 + 400 * rage
    assert (t.rage_katana, t.rage_bazooka) == (0.2, 0.3)


def test_attack_numbers_can_be_overridden():
    t = from_dict({"rocket_speed": 600, "grab_chance_per_rage": 0, "rage_bazooka": 0.5})
    assert t.rocket(0.0) == 600.0 and t.rocket(1.0) == 1000.0
    assert t.grab(1.0) == 0.3
    assert t.rage_bazooka == 0.5 and t.rage_katana == 0.2


def test_behaviour_thresholds_match_the_old_hardcoded_numbers():
    t = Tuning()
    assert (t.rage_chase_after_taunt, t.rage_getup_notice, t.rage_kick) == (0.3, 0.35, 0.3)
    for rage in (0.0, 0.3, 0.5, 1.0):
        for dt in (0.016, 0.1, 1.0):
            assert t.kick_chance(rage, dt) == 0.3 * rage * dt


def test_behaviour_thresholds_can_be_overridden():
    t = from_dict({"rage_kick": 0.6, "kick_chance_per_rage_s": 0.0, "rage_getup_notice": 0.1})
    assert t.rage_kick == 0.6 and t.kick_chance(1.0, 1.0) == 0.0
    assert t.rage_getup_notice == 0.1 and t.rage_chase_after_taunt == 0.3


def test_window_attack_and_parry_numbers_match_the_old_hardcoded_formulas():
    t = Tuning()
    assert (t.rage_window_katana, t.window_katana_chance) == (0.5, 0.5)
    assert (t.rage_parry_anytime, t.parry_chance) == (0.3, 0.35)
    for rage in (0.0, 0.2, 0.5, 0.9, 1.0):
        assert t.attack_pause(rage) == max(0.8, 2.8 - 1.8 * rage)


def test_window_attack_and_parry_numbers_can_be_overridden():
    t = from_dict({"parry_chance": 0.0, "attack_pause_s": 5.0, "attack_pause_min_s": 2.0})
    assert t.parry_chance == 0.0 and t.rage_parry_anytime == 0.3
    assert t.attack_pause(0.0) == 5.0 and t.attack_pause(1.0) == 3.2
    assert from_dict({"attack_pause_per_rage": 10.0}).attack_pause(1.0) == 0.8


def test_punch_notice_and_bazooka_fire_match_the_old_hardcoded_formulas():
    t = Tuning()
    for rage in (0.0, 0.25, 0.5, 0.9, 1.0):
        assert t.punch(rage) == 90 + 120 * rage
        assert t.crack(rage) == 0.4 + 0.6 * rage
        for dt in (0.016, 0.033, 1.0):
            assert t.notice_chance(rage, dt) == (0.2 + 1.3 * rage) * dt
            assert t.bazooka_fire_chance(rage, dt) == (0.15 + 0.6 * rage) * dt


def test_punch_notice_and_bazooka_fire_can_be_overridden():
    t = from_dict(
        {"punch_push": 200.0, "crack_chance": 0.0, "crack_chance_per_rage": 0.0, "notice_per_s_per_rage": 0.0}
    )
    assert t.punch(1.0) == 320.0 and t.crack(1.0) == 0.0
    assert t.notice_chance(1.0, 1.0) == 0.2
    assert t.bazooka_fire_chance(1.0, 1.0) == 0.75
