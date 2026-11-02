import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication
from test_dude import _make, _run, dd

from life import TIERS, Precip, Save


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _quiet(seed):
    w32, clock, dude = _make(seed)
    dude.terror.enabled = dude.war.enabled = dude.arsenal.enabled = False
    _run(dude, clock, 60)
    dude.x = dude.world.left + 300.0
    dude.y, dude.vx, dude.vy = dude.world.floor_at(dude.x), 0.0, 0.0
    dude.on_ground, dude.plat_hwnd, dude.rage = True, None, 0.0
    dude.set_state(dd.IDLE, 5.0)
    w32.cursor = (int(dude.world.right - 5), int(dude.world.top + 5))
    return w32, clock, dude


def _paint(dude):
    img = QImage(240, 210, QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    qp = QPainter(img)
    try:
        dude.life.paint(qp, dd.FX, dd.FY, dude.pose, dude.f)
    finally:
        qp.end()


def _until(dude, clock, cond, secs):
    for _ in range(int(secs * 60)):
        clock[0] += 1 / 60
        dude.tick(1 / 60)
        if cond():
            return True
    return False


def test_watches_with_popcorn_when_you_watch(app):
    w32, clock, dude = _quiet(50)
    w32.title = "Spiksplinter - VLC media player"
    dude.life.cd["watch"] = 0.0
    assert _until(dude, clock, lambda: dude.state == "watch", 60)
    _run(dude, clock, 30)
    _paint(dude)
    assert dude.errors == 0


def test_dances_on_the_beat(app):
    _w32, clock, dude = _quiet(51)
    life = dude.life
    life.music.feed = lambda t: 0.7 if (t % 0.5) < 0.04 else 0.12
    _run(dude, clock, 60 * 3)
    assert life.music.playing
    dude.set_state(dd.IDLE, 5.0)
    assert life.trigger("dance")
    _run(dude, clock, 60 * 4)
    assert dude.state == "dance" and life.goal["beats"] >= 4
    life.goal["move"] = 3
    _paint(dude)
    assert dude.errors == 0


def test_sleeps_at_night_and_wakes_up_furious(app):
    w32, clock, dude = _quiet(52)
    life = dude.life
    life.hour_fn = lambda: 3
    assert life.trigger("sleep")
    _run(dude, clock, 60 * 3)
    assert dude.state == "sleep"
    _paint(dude)
    w32.cursor = (int(dude.x), int(dude.y - 20))
    _run(dude, clock, 60)
    assert dude.state != "sleep" and dude.rage >= 0.6 and dude.errors == 0


def test_coffee_then_back_to_normal(app):
    _w32, clock, dude = _quiet(53)
    assert dude.life.trigger("coffee")
    _run(dude, clock, 30)
    _paint(dude)
    _run(dude, clock, 60 * 9)
    assert dude.state != "coffee" and dude.errors == 0


def test_levels_unlock_weapons(app):
    _w32, _clock, dude = _quiet(54)
    life, ar = dude.life, dude.arsenal
    dude.rage = 1.0
    far = (dude.x + 300, dude.y - 60)
    assert life.level == 1
    assert {ar.pick(far) for _ in range(300)} <= set(TIERS[0])
    life.gain(900)
    assert life.level == 5 and life.fx  # LEVEL UP pop
    assert "chainsaw" in {ar.pick(far) for _ in range(400)}


def test_grudge_builds_up(app):
    _w32, _clock, dude = _quiet(55)
    life = dude.life
    for _ in range(10):
        life.dude_hit("punched")
    assert life.save["grudge"] >= 2.9 and life.save["punched"] == 10


def test_recycle_bin(app):
    _w32, clock, dude = _quiet(56)
    life = dude.life
    hx, hy = dude.limb("hip")
    dude.terror.probe.icons = [("Prullenbak", (hx - 30, hy - 30, hx + 30, hy + 30))]
    dude.on_ground = False
    dude.set_state(dd.RAGDOLL)
    _run(dude, clock, 2)
    assert dude.state == "binned" and life.hidden()
    _run(dude, clock, 60 * 7)
    assert dude.state != "binned" and life.soot > 0 and dude.rage > 0.8
    _paint(dude)
    assert life.save["binned"] == 1 and dude.errors == 0


def test_duel_best_of_three(app):
    w32, clock, dude = _quiet(57)
    life = dude.life
    w32.cursor = (int(dude.x + 150), int(dude.y - 60))
    assert life.toggle_duel()
    du = life.duel

    def fight():
        assert _until(dude, clock, lambda: du.phase == "fight", 6)

    fight()
    for _ in range(5):
        life.dude_hit("punched")
    _run(dude, clock, 5)
    assert du.score == [1, 0]
    fight()
    du.hp[0] = 0
    _run(dude, clock, 5)
    assert du.score == [1, 1]
    fight()
    for _ in range(5):
        life.dude_hit("punched")
    assert _until(dude, clock, lambda: life.duel is None, 6)
    assert life.save["duels_lost"] == 1 and dude.terror.enabled is False and dude.errors == 0


def test_taskbar_clock_and_start_button(app):
    w32, clock, dude = _quiet(58)
    life = dude.life
    floor = dude.world.floor_at(dude.x)
    life.parts = {"start": (0, floor, 48, floor + 40),
                  "clock": (dude.world.right - 140, floor, dude.world.right - 70, floor + 40)}
    assert life.trigger("clock")
    assert _until(dude, clock, lambda: life.goal.get("phase") == "sit", 15)
    _run(dude, clock, 30)
    assert dude.state == "sit" and dude.y == floor + 20
    w32.cursor = (int(dude.x), int(dude.y - 40))
    _run(dude, clock, 10)
    assert dude.state != "sit"
    w32.cursor = (int(dude.world.right - 5), int(dude.world.top + 5))
    _run(dude, clock, 60 * 2)
    dude.rage = 0.0
    played = []
    real_play = dude.terror.sfx.play
    dude.terror.sfx.play = lambda name: (played.append(name), real_play(name))
    dude.set_state(dd.IDLE, 5.0)
    dude.on_ground = True
    assert life.trigger("start")
    assert _until(dude, clock, lambda: "bonk" in played, 20)
    assert dude.errors == 0


def test_weather_showers_umbrella_and_snowman(app):
    _w32, clock, dude = _quiet(59)
    life = dude.life
    life.weather.code = 61
    life.cd["shower"] = 0.0
    _run(dude, clock, 5)
    assert isinstance(life.precip, Precip) and life.precip.kind == "rain"
    dude.set_state(dd.IDLE, 5.0)
    _run(dude, clock, 2)
    assert dude.pose.upper[1] < -2.5
    _paint(dude)
    _run(dude, clock, 60 * 31)
    assert life.precip is None
    life.weather.code = None
    dude.set_state(dd.IDLE, 5.0)
    dude.on_ground = True
    life.start_shower("snow", dur=5.0)
    assert dude.state == "build"
    _run(dude, clock, 60 * 4)
    assert life.marks and dude.errors == 0


def test_mini_dudes_slap_and_go_poof(app):
    w32, clock, dude = _quiet(60)
    life = dude.life
    assert life.trigger("minions") and len(life.minions) == 3
    floor = dude.world.floor_at(dude.x)
    for _ in range(60 * 8):
        clock[0] += 1 / 60
        w32.cursor = (int(dude.x + 160), int(floor - 20))
        dude.tick(1 / 60)
        dude.rage = 0.0
        dude.set_state(dd.IDLE, 5.0)
    assert life.save["hits"] >= 1
    life.minions[0].dead = True
    _run(dude, clock, 1)
    assert len(life.minions) == 2
    dude.release_everything()
    assert not life.minions and w32.pos == w32.orig and dude.errors == 0


def test_home_assistant_power_cut_restores_lights(app):
    _w32, _clock, dude = _quiet(61)
    ha = dude.life.ha
    calls = []

    def http(method, path, body=None):
        calls.append((path, body))
        if method == "GET":
            return [{"entity_id": "light.desk", "state": "on"}, {"entity_id": "light.hall", "state": "off"},
                    {"entity_id": "switch.tv", "state": "on"}]
        return None

    ha.url, ha.token = "http://ha", "t"
    ha.http, ha.spawn, ha.sleep = http, (lambda fn: fn()), (lambda s: calls.append(("sleep", s)))
    assert dude.life.trigger("power")
    assert [c[0] for c in calls] == ["/api/states", "/api/services/scene/create", "/api/services/light/turn_off",
                                     "sleep", "/api/services/scene/turn_on"]
    assert calls[2][1] == {"entity_id": ["light.desk"]} and not ha.active


def test_save_roundtrip(tmp_path):
    p = tmp_path / "save.json"
    s = Save(p)
    s["xp"] = 123
    s.write()
    assert Save(p)["xp"] == 123


def test_starts_with_a_grudge(app, tmp_path, monkeypatch):
    import life

    (tmp_path / "dude_save.json").write_text('{"grudge": 8, "xp": 100}', encoding="utf-8")
    monkeypatch.setattr(life, "HERE", tmp_path)
    real_save = life.Save
    monkeypatch.setattr(life, "Save", lambda path: real_save(tmp_path / "dude_save.json"))
    _w32, clock, dude = _make(62)
    _run(dude, clock, 2)
    assert dude.life.save["grudge"] > 7 and dude.rage >= 0.45 and dude.life.level == 2 and dude.errors == 0
