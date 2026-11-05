import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import random

import pytest
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication
from test_dude import _run, dd
from test_life import _quiet

import vandal
from graffiti import PIECES, TAGS, THROWUPS, Piece
from terror import Graffiti
from vandal import HOLE_LIFE, PATCH_LIFE, WallHole, WallPiece, cut_out


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _bare(seed):
    """A dude on the floor of an empty desktop (no windows in the way)."""
    w32, clock, dude = _quiet(seed)
    w32.wins = []
    dude.world.refresh()
    dude.terror.enabled = True
    return w32, clock, dude


@pytest.mark.parametrize("style", ["tag", "throwup", "piece"])
def test_every_style_paints(app, style):
    rng = random.Random(3)
    for text in (None, "LOS MOKUMOS", "020"):
        p = Piece(style, text, scale=0.9, rng=rng)
        w, h = p.size()
        assert 100 < w < 1600 and 60 < h < 900
        img = QImage(w, h, QImage.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))
        qp = QPainter(img)
        p.paint(qp, w / 2, h / 2, 0.6)
        p.paint(qp, w / 2, h / 2)
        qp.end()
        painted = sum(img.pixelColor(x, y).alpha() > 0 for x in range(0, w, 7) for y in range(0, h, 7))
        assert painted > 20


def test_sizes_and_heights_vary(app):
    _w32, _clock, dude = _bare(62)
    scales, ys = set(), []
    for _ in range(8):
        dude.set_state(dd.IDLE, 5.0)
        dude.on_ground = True
        assert dude.vandal.start_spray()
        j = dude.vandal.job
        scales.add(round(j["piece"].scale, 2))
        ys.append(j["cy"])
        dude.vandal.release()
        dude.vandal.clear()
    assert len(scales) >= 5
    assert max(ys) - min(ys) > 120


def test_words_are_mokum():
    assert "MOKUM" in THROWUPS and "020" in THROWUPS
    assert "los mokumos" in TAGS and "grand theft fiets" in TAGS
    assert "AMSTERDAM" in PIECES


def test_graffiti_goes_high_when_no_wallpaper_is_free(app):
    w32, clock, dude = _quiet(51)
    w32.wall_origin = lambda: None  # no wallpaper layer: classic overlay
    for _ in range(4):
        dude.terror.graffiti and dude.terror.clear_graffiti()
        dude.set_state(dd.IDLE, 5.0)
        dude.on_ground = True
        assert dude.terror._graffiti()
        g = dude.terror.graffiti[-1]
        assert isinstance(g, Graffiti)
        s = dude.world.screen_at(dude.x)
        cy = g.y() + g.height() / 2
        assert g.y() + g.height() <= s[1] + (s[4] - s[1]) * vandal.OVERLAY_LOW + 2 or cy < s[1] + g.height(), \
            "out of the way of where you type"
        _spray_done(dude, clock)


def _spray_done(dude, clock, secs=6):
    for _ in range(int(secs * 60)):
        clock[0] += 1 / 60
        dude.tick(1 / 60)
        if not dude.vandal.job:
            return
    raise AssertionError("still spraying")


def test_he_jumps_up_and_sprays_it_himself(app):
    w32, clock, dude = _quiet(60)
    w32.wall_origin = lambda: None
    y0 = dude.y
    assert dude.vandal.start_spray()
    j = dude.vandal.job
    g = j["w"]
    assert g.progress == 0.0 and not g.auto, "nothing appears until he's there"
    seen, highest, progress_seen = set(), y0, []
    for _ in range(60 * 6):
        clock[0] += 1 / 60
        dude.tick(1 / 60)
        if not dude.vandal.job:
            break
        seen.add(dude.vandal.job["phase"])
        highest = min(highest, dude.y)
        if dude.vandal.job["phase"] == "spray":
            progress_seen.append(g.progress)
            hx, hy = dude.limb("hand_a")
            tx, ty = dude.vandal.spray_target(g.progress, dude.vandal.job["t"])
            assert abs(hx - tx) < 12 and abs(hy - ty) < 12, "his hand is on the spray edge"
    assert seen == {"crouch", "fly", "spray"}
    assert highest < y0 - 150, "he went up there"
    assert progress_seen == sorted(progress_seen) and g.progress == 1.0
    assert dude.vandal.land_watch > 0 or any(isinstance(w, vandal.Dust) for w in dude.vandal.fx)
    landed = False
    for _ in range(60 * 4):
        clock[0] += 1 / 60
        dude.tick(1 / 60)
        landed = landed or dude.on_ground
    assert landed and dude.vandal.land_watch == 0 and dude.errors == 0, "lands, with a puff of dust"


def test_grabbed_mid_spray_the_paint_finishes(app):
    w32, clock, dude = _quiet(61)
    w32.wall_origin = lambda: None
    assert dude.vandal.start_spray()
    g = dude.vandal.job["w"]
    _run(dude, clock, 50)
    dude.set_state("held", 1.0)
    _run(dude, clock, 120)
    assert not dude.vandal.job and g.progress == 1.0


def test_graffiti_lands_on_the_wallpaper_when_desktop_is_bare(app):
    _w32, clock, dude = _bare(52)
    assert dude.terror._graffiti()
    assert dude.terror.graffiti == []
    assert len(dude.vandal.wall) == 1 and isinstance(dude.vandal.wall[0], WallPiece)
    _spray_done(dude, clock)
    assert dude.vandal.wall[0].progress == 1.0
    l, t, r, b = dude.vandal.wall[0].rect_
    assert dude.vandal.free(l, t, r, b)
    _run(dude, clock, 120)
    assert dude.vandal.wall and dude.errors == 0
    dude.clear_graffiti()
    assert dude.vandal.wall == []


def test_wall_spot_avoids_windows(app):
    _w32, _clock, dude = _quiet(53)
    v = dude.vandal
    for win in dude.world.wins:
        l, t, _r, _b = win.rect
        assert not v.free(l + 5, t + 5, l + 50, t + 50)
    for _ in range(10):
        spot = v.spot_for(200, 120)
        if spot:
            x, y = spot
            assert v.free(x - 100, y - 60, x + 100, y + 60)


def test_punch_a_hole_then_tape_it(app):
    _w32, clock, dude = _bare(54)
    assert dude.vandal.start("hole")
    assert dude.state == "vandal"
    for _ in range(60 * 12):
        clock[0] += 1 / 60
        dude.tick(1 / 60)
        if not dude.vandal.job:
            break
    assert not dude.vandal.job and dude.errors == 0
    holes = [w for w in dude.vandal.wall if isinstance(w, WallHole)]
    assert len(holes) == 1
    h = holes[0]
    for _ in range(int(HOLE_LIFE * 10)):
        h.step(0.1)
    assert h.patched
    assert not h.step(PATCH_LIFE + 1), "taped up and gone"


def test_hole_rat_peeks(app):
    w32, _clock, _dude = _bare(55)
    h = WallHole(w32, 400, 300, random.Random(1))
    seen = 0.0
    for _ in range(300):
        h.step(0.05)
        seen = max(seen, h.rat_k)
        h.repaint()
    assert seen > 0.9
    h.kill()


def test_icon_football(app):
    w32, clock, dude = _bare(56)
    dude.terror.probe.icons = [("Prullenbak", (40, 40, 110, 116))]
    assert dude.vandal.start("football")
    j = dude.vandal.job
    assert j["kind"] == "football" and j["ball"] in dude.vandal.fx
    kicked = 0
    for _ in range(60 * 40):
        clock[0] += 1 / 60
        w32.cursor = (790, 10)
        dude.tick(1 / 60)
        if dude.vandal.job:
            kicked = max(kicked, dude.vandal.job.get("kicks", 0))
        else:
            break
    assert not dude.vandal.job, "the icon always goes home"
    assert dude.errors == 0
    assert not any(isinstance(w, (vandal.Ball, vandal.Patch)) for w in dude.vandal.fx)
    assert dude.state != "vandal"


def test_ball_goes_home_when_he_gets_grabbed(app):
    _w32, clock, dude = _bare(57)
    dude.terror.probe.icons = [("Prullenbak", (40, 40, 110, 116))]
    assert dude.vandal.start("football")
    _run(dude, clock, 30)
    dude.set_state("held", 1.0)
    for _ in range(60 * 3):
        clock[0] += 1 / 60
        dude.tick(1 / 60)
    assert not dude.vandal.job


def test_you_can_kick_the_ball_too(app):
    _w32, _clock, dude = _bare(58)
    dude.terror.probe.icons = [("Prullenbak", (40, 40, 110, 116))]
    assert dude.vandal.start("football")
    j = dude.vandal.job
    vy = j["vy"]
    dude.vandal.user_kick()
    assert j["vy"] < vy - 100


def test_cut_out_removes_the_wallpaper_around_an_icon(app):
    wall = QImage(40, 40, QImage.Format_ARGB32)
    wall.fill(QColor(30, 60, 200))
    icon = QImage(wall)
    p = QPainter(icon)
    p.fillRect(10, 10, 20, 20, QColor(250, 200, 20))
    p.end()
    out = cut_out(icon, wall)
    assert out.pixelColor(2, 2).alpha() == 0
    assert out.pixelColor(20, 20).alpha() == 255
    assert cut_out(icon, None).pixelColor(2, 2).alpha() == 255


def test_release_keeps_the_wall_but_stops_the_game(app):
    _w32, clock, dude = _bare(59)
    dude.terror.probe.icons = [("Prullenbak", (40, 40, 110, 116))]
    assert dude.vandal.start_piece()
    _spray_done(dude, clock)
    _run(dude, clock, 240)  # he lands first
    assert dude.vandal.start("football")
    dude.release_everything()
    assert not dude.vandal.job and dude.vandal.fx == []
    assert len(dude.vandal.wall) == 1
