import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication
from test_dude import _run, dd
from test_life import _quiet, _until


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _fish(x, y, beh="swimFree", fid=7):
    return {"id": fid, "name": "Bram", "x": x, "y": y, "l": x - 40, "t": y - 80, "r": x + 40, "bo": y + 10,
            "vx": 0.0, "vy": 0.0, "right": True, "beh": beh, "scale": 1.0}


def _setup(seed):
    w32, clock, dude = _quiet(seed)
    dude.aqua.enabled = False
    floor = dude.world.floor_at(dude.x)
    dude.aqua.link.fish = {7: _fish(dude.x + 150, floor - 30)}
    return w32, clock, dude


def _ops(dude, kind):
    return [o for o in dude.aqua.link.pending if o["op"] == kind]


def _paint(dude):
    img = QImage(240, 210, QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    qp = QPainter(img)
    try:
        dude.aqua.paint(qp, dd.FX, dd.FY, dude.pose, dude.f)
    finally:
        qp.end()


def test_rides_a_cuttlefish_until_bucked_off(app):
    _w32, clock, dude = _setup(70)
    aq = dude.aqua
    assert aq.start("ride", 7)
    assert _until(dude, clock, lambda: aq.job.get("phase") == "ride", 8)
    assert _ops(dude, "ride")
    fish = aq.link.fish[7]
    fish["beh"], fish["x"], fish["y"], fish["t"] = "dude-ride", fish["x"] + 200, fish["y"] - 150, fish["t"] - 150
    fish["back"] = fish["y"] - 40
    _run(dude, clock, 30)
    assert dude.state == "aqua" and dude.x == fish["x"] and dude.y == fish["back"] + 18 and aq.FROZEN
    _paint(dude)
    fish["beh"] = "angry"
    _run(dude, clock, 2)
    assert dude.state == "ragdoll" and aq.stats["ride"] == 1 and dude.errors == 0


def test_carries_and_throws_one(app):
    _w32, clock, dude = _setup(71)
    aq = dude.aqua
    assert aq.start("carry", 7)
    assert _until(dude, clock, lambda: aq.stats["carry"] == 1, 12)
    holds, rel = _ops(dude, "hold"), _ops(dude, "release")
    assert len(holds) == 1 and rel and abs(rel[0]["vx"]) == 950 and dude.errors == 0


def test_pets_one(app):
    _w32, clock, dude = _setup(72)
    aq = dude.aqua
    dude.rage = 0.6
    assert aq.start("pet", 7)
    assert _until(dude, clock, lambda: aq.stats["pet"] == 1, 12)
    assert len(_ops(dude, "pet")) == 3 and dude.rage < 0.6 and dude.errors == 0


def test_fights_one_and_gets_inked(app):
    _w32, clock, dude = _setup(73)
    aq = dude.aqua
    assert aq.start("fight", 7)
    assert _until(dude, clock, lambda: len(_ops(dude, "hit")) == 1, 8)
    aq.link.events.append({"ev": "ink", "id": 7, "x": dude.x, "y": dude.y - 60})
    _run(dude, clock, 2)
    assert dude.state == "stunned" and not aq.job
    assert aq.start("fight", 7) if dude.state != "stunned" else True
    _run(dude, clock, 60 * 2)
    dude.set_state(dd.IDLE, 5.0)
    assert aq.start("fight", 7)
    assert _until(dude, clock, lambda: aq.stats["fight"] == 1, 15)
    assert len(_ops(dude, "hit")) >= 4 and dude.errors == 0


def test_eats_one_for_real(app):
    _w32, clock, dude = _setup(74)
    aq = dude.aqua
    assert aq.start("eat", 7)
    assert _until(dude, clock, lambda: bool(_ops(dude, "eat")), 12)
    assert _ops(dude, "hold")
    aq.link.events.append({"ev": "eaten", "id": 7, "name": "Bram"})
    _run(dude, clock, 2)
    assert aq.stats["eat"] == 1 and dude.life.save["fish"] == 1 and dude.state != "aqua" and dude.errors == 0


def test_last_cuttlefish_is_refused(app):
    _w32, clock, dude = _setup(75)
    aq = dude.aqua
    assert aq.start("eat", 7)
    assert _until(dude, clock, lambda: bool(_ops(dude, "eat")), 12)
    aq.link.events.append({"ev": "refused", "id": 7})
    _run(dude, clock, 2)
    assert _ops(dude, "release") and aq.stats["eat"] == 0 and dude.state != "aqua"


def test_punch_makes_him_drop_the_fish(app):
    _w32, clock, dude = _setup(76)
    aq = dude.aqua
    assert aq.start("carry", 7)
    assert _until(dude, clock, lambda: aq.job.get("phase") == "act", 8)
    dude.press = (dude.x - 10, dude.y - 50)
    from test_dude import _Ev

    dude.mouseReleaseEvent(_Ev(dude.x - 10, dude.y - 50))
    _run(dude, clock, 2)
    assert _ops(dude, "release") and not aq.job and dude.errors == 0


def test_fish_that_swims_off_is_given_up(app):
    _w32, clock, dude = _setup(77)
    aq = dude.aqua
    aq.link.fish[7]["y"] -= 250  # out of jumping reach
    assert aq.start("pet", 7)
    assert _until(dude, clock, lambda: dude.state != "aqua", 12) and aq.stats["pet"] == 0
