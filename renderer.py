"""Paints graffiti pieces in a helper process, so the dude never stutters.

One big piece takes 100-250 ms to draw (overspray, 3D drop, outlines, drips). Python threads share one lock (the
GIL), so drawing it anywhere in the dude's own process freezes his animation for that long. The helper process
has its own Python: it rebuilds the piece from its spec (same seed, same piece) and sends back the finished
image. The dude then only reveals that image while he sprays, which costs about a millisecond per frame.

No helper (tests, or it failed to start): pieces are drawn in-process as before.
"""

from __future__ import annotations

import itertools
import os
import queue

from PySide6.QtGui import QImage


def _work(inq, outq):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication([])  # noqa: F841 - fonts need a gui application
    from graffiti import Piece, render

    while True:
        job = inq.get()
        if job is None:
            return
        jid, (style, text, scale, seed) = job
        try:
            img = render(Piece(style, text, scale, seed=seed))
            outq.put((jid, img.width(), img.height(), bytes(img.constBits())))
        except Exception as e:  # noqa: BLE001
            outq.put((jid, 0, 0, repr(e).encode()))


class Renderer:
    def __init__(self, real: bool):
        self.real = real
        self.proc = None
        self.ids = itertools.count(1)
        self.done: dict[int, QImage | None] = {}

    def start(self):
        if not self.real or self.proc is not None:
            return
        try:
            import multiprocessing as mp

            ctx = mp.get_context("spawn")
            self.inq, self.outq = ctx.Queue(), ctx.Queue()
            self.proc = ctx.Process(target=_work, args=(self.inq, self.outq), daemon=True, name="graffiti")
            self.proc.start()
        except Exception as e:  # noqa: BLE001 - no helper: draw in-process
            from terror import _log

            _log(f"graffiti helper not started: {e!r}")
            self.proc = None

    def alive(self) -> bool:
        return self.proc is not None and self.proc.is_alive()

    def request(self, piece) -> int | None:
        if piece.seed is None or not self.alive():
            return None
        jid = next(self.ids)
        self.inq.put((jid, piece.spec))
        return jid

    def poll(self, jid) -> QImage | None:
        """The finished image, or None if it isn't there yet. A failed job also gives None (and stays failed)."""
        if jid is None:
            return None
        while True:
            try:
                rid, w, h, data = self.outq.get_nowait()
            except (queue.Empty, OSError, EOFError):
                break
            self.done[rid] = QImage(data, w, h, QImage.Format_ARGB32_Premultiplied).copy() if w else None
        return self.done.pop(jid, None)

    def stop(self):
        if self.alive():
            try:
                self.inq.put(None)
            except Exception:  # noqa: BLE001, S110
                pass
