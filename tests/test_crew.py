import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication
from test_life import _quiet

from cleanup import Worker
from graffiti import Piece, paint_cached, render
from terror import Graffiti
from vandal import WallHole, WallPiece


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _mess(dude, w32):
    """Two tags on top of the screen, a piece on the wallpaper and a hole."""
    t = dude.terror
    for x, y in ((250, 90), (560, 130)):
        g = Graffiti(x, y, Piece("tag", "dude020", 0.5, seed=x), auto=True)
        g.progress = 1.0
        t.graffiti.append(g)
    wp = WallPiece(w32, 420, 260, Piece("throwup", "MOKUM", 0.5, seed=3))
    wp.progress = 1.0
    dude.vandal.wall += [wp, WallHole(w32, 300, 420)]


def _run_until(dude, clock, cond, secs):
    for _ in range(int(secs * 60)):
        clock[0] += 1 / 60
        dude.tick(1 / 60)
        if cond():
            return True
    return False


def test_crew_washes_it_all_off(app):
    w32, clock, dude = _quiet(80)
    dude.terror.enabled = False
    _mess(dude, w32)
    crew = dude.crew
    assert crew.start()
    assert crew.workers and all(isinstance(w, Worker) for w in crew.workers)
    erased = []
    assert _run_until(dude, clock, lambda: (erased.extend(g.erase for g in dude.terror.graffiti) or True)
                      and not crew.active, 60), "they finish and drive off"
    assert dude.terror.graffiti == []
    assert not [w for w in dude.vandal.wall if isinstance(w, WallPiece)]
    holes = [w for w in dude.vandal.wall if isinstance(w, WallHole)]
    assert all(h.patched for h in holes), "the hole is plastered"
    assert any(0 < e < 1 for e in erased), "washed off bit by bit, not popped away"
    assert dude.errors == 0


def test_crew_goes_up_on_the_lift(app):
    _w32, clock, dude = _quiet(81)
    dude.terror.enabled = False
    g = Graffiti(400, 80, Piece("tag", "hoog", 0.5, seed=9), auto=True)
    g.progress = 1.0
    dude.terror.graffiti.append(g)
    assert dude.crew.start()
    top = 0.0
    for _ in range(60 * 30):
        clock[0] += 1 / 60
        dude.tick(1 / 60)
        top = max([top] + [w.lift for w in dude.crew.workers])
        if not dude.crew.active:
            break
    assert top > 200 and not dude.terror.graffiti


def test_nothing_to_clean_nobody_comes(app):
    _w32, _clock, dude = _quiet(82)
    assert not dude.crew.start()


def test_they_come_by_themselves_when_it_piles_up(app):
    _w32, clock, dude = _quiet(83)
    dude.terror.enabled = False
    for i in range(6):
        g = Graffiti(150 + i * 90, 100, Piece("tag", f"t{i}", 0.4, seed=i), auto=True)
        g.progress = 1.0
        dude.terror.graffiti.append(g)
    dude.crew.cd, dude.crew.check = 0.0, 0.0
    assert _run_until(dude, clock, lambda: dude.crew.active, 2)


def test_washed_off_part_is_gone(app):
    p = Piece("throwup", "MOKUM", 0.8, seed=4)
    img = render(p)
    w, h = p.size()
    out = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    out.fill(0)
    qp = QPainter(out)
    paint_cached(qp, w, h, p, img, 1.0, erase=0.5)
    qp.end()
    left = sum(out.pixelColor(x, y).alpha() for x in range(0, int(w * 0.48), 4) for y in range(0, h, 4))
    right = sum(out.pixelColor(x, y).alpha() for x in range(int(w * 0.52), w, 4) for y in range(0, h, 4))
    assert left == 0 and right > 0
