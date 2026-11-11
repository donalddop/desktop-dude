import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time

import pytest
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from graffiti import Piece, paint_cached, render
from renderer import Renderer


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_same_seed_same_piece(app):
    a, b = Piece(None, None, 1.2, seed=11), Piece(None, None, 1.2, seed=11)
    assert (a.style, a.text, a.angle, a.size(), a.drips) == (b.style, b.text, b.angle, b.size(), b.drips)
    assert a.spec == (None, None, 1.2, 11)


def test_helper_process_paints_it_off_the_main_thread(app):
    r = Renderer(True)
    r.start()
    try:
        assert r.alive()
        p = Piece("piece", "MOKUM", 1.4, seed=7)
        jid = r.request(p)
        assert jid is not None
        img, t0, gaps, last = None, time.perf_counter(), [], time.perf_counter()
        while img is None and time.perf_counter() - t0 < 30:
            img = r.poll(jid)
            time.sleep(0.005)
            now = time.perf_counter()
            if img is None:  # the frame that receives (and copies) the image doesn't count
                gaps.append(now - last)
            last = now
        assert img is not None, "the helper sent the piece back"
        assert (img.width(), img.height()) == p.size()
        # painting it here would block for 100-250 ms; slow shared CI machines hiccup up to ~70 ms on their own`n        assert max(gaps) < 0.09, "the main thread never waited on the painting"
        assert sum(img.pixelColor(x, y).alpha() > 0 for x in range(0, img.width(), 9)
                   for y in range(0, img.height(), 9)) > 50
    finally:
        r.stop()


def test_no_helper_means_no_ticket(app):
    r = Renderer(False)
    r.start()
    assert r.request(Piece("tag", seed=1)) is None and r.poll(None) is None


def test_revealing_a_piece_is_cheap(app):
    p = Piece("piece", "LOS MOKUMOS", 1.8, seed=3)
    img = render(p)
    w, h = p.size()
    target = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    t0 = time.perf_counter()
    for i in range(60):
        target.fill(0)
        qp = QPainter(target)
        paint_cached(qp, w, h, p, img, i / 59)
        qp.end()
    per_frame = (time.perf_counter() - t0) / 60
    assert per_frame < 0.008, f"{per_frame * 1000:.1f} ms per frame"
