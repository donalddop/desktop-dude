"""The graffiti removal crew: two or three council workers in hi-vis, each driving a little scissor lift.

They roll in from the side of the screen, drive to every piece of his graffiti (on top of your windows or on
your wallpaper), raise the lift and blast it off with a pressure washer, left to right. Holes in the wall get
plastered. The dude hates it. Call them from the tray, or they come by themselves when it gets too much.
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPen, QPolygonF

from arsenal import PopText
from terror import LINES
from vandal import HOLE_LIFE, WallHole, WallPiece
from warfare import FxWindow, _painter

LINES.update({
    "crew": ["HÉ! Dat is KUNST!", "Van mijn muur afblijven, sukkels!", "Handhaving? Wollah ik was het niet",
             "Kankerzooi, al mijn werk!"],
    "crew_gone": ["Mooi schoon. Lekker vers canvas, mattie", "Ze komen toch niet terug?",
                  "Belastinggeld verspild, ik spuit gewoon opnieuw"],
})
CREW_SAYS = ["Gemeente! Opzij jongen", "Even wegspuiten hoor", "Wéér die gast", "Wie doet nou zoiets",
             "Om tien uur koffie", "Psssshhh"]

_rng = random.Random()
WIN_W, WX = 240, 70  # worker window width; his feet sit this far from its left edge
BASE, DECK = 22.0, 6.0  # lift chassis and platform heights
DRIVE = 190.0  # px/s along the floor
LIFT = 300.0  # px/s up and down
WASH = 420.0  # px/s the jet eats through a piece
SCALE = 0.72  # workers are a bit smaller than the dude


def _rect(w):
    """Screen rect (l, t, r, b) of a graffiti widget, whichever layer it lives on."""
    if isinstance(w, (WallPiece, WallHole)):
        return w.rect_
    return (w.x(), w.y(), w.x() + w.width(), w.y() + w.height())


class Worker(FxWindow):
    """One crew member on his scissor lift. The window is a full-height column so the lift can grow."""

    def __init__(self, crew, x, side):
        wd = crew.d.world
        self.crew, self.top = crew, wd.top
        super().__init__(WIN_W, int(wd.bottom - wd.top) + 10)
        self.x, self.lift, self.f = x, 0.0, -side
        self.target, self.phase, self.t, self.erase = None, "drive", 0.0, 0.0
        self.aim = (0.0, 0.0)
        self.wheel, self.say_cd = 0.0, _rng.uniform(1.5, 4.0)
        self.place()
        self.show()

    # ---- geometry
    def floor(self):
        return self.crew.d.world.floor_at(self.x)

    def feet(self):
        return self.floor() - BASE - DECK - self.lift

    def place(self):
        self.move(round(self.x - WX), round(self.top))

    def hand(self):
        pts = self.crew.kit["skeleton"](self.pose(), self.f)
        hx, hy = pts["hand_a"]
        return self.x + hx * SCALE, self.feet() + hy * SCALE

    def pose(self):
        k = self.crew.kit
        if self.phase == "wash":
            s = math.sin(self.t * 9) * 0.12
            return k["Pose"](0.12, (0.12, -0.12), (0.06, -0.06), (1.45 + s, 1.25 + s), (1.6 + s, 1.4 + s))
        return k["pose_stand"](self.t)

    # ---- per frame
    def drive_to(self, x, dt):
        dx = x - self.x
        step = min(abs(dx), DRIVE * dt)
        self.x += math.copysign(step, dx)
        self.wheel += step / 6
        if abs(dx) > 2:
            self.f = 1 if dx > 0 else -1
        return abs(dx) <= 2

    def lift_to(self, h, dt):
        h = max(0.0, h)
        d = h - self.lift
        self.lift += math.copysign(min(abs(d), LIFT * dt), d)
        return abs(d) < 1

    def step(self, dt) -> bool:
        self.t += dt
        c = self.crew
        if self.target is not None and not c.alive(self.target):
            self.target, self.phase = None, "lower"
        if self.phase == "leave":
            wd = c.d.world
            edge = wd.left - 140 if self.f < 0 else wd.right + 140
            if self.lift_to(0, dt) and self.drive_to(edge, dt):
                self.kill()
                return False
        elif self.phase == "lower":
            if self.lift_to(0, dt):
                self.target = c.claim(self)
                self.phase = "drive" if self.target is not None else "leave"
                if self.target is None:
                    wd = c.d.world
                    self.f = -1 if self.x - wd.left < wd.right - self.x else 1
        elif self.target is not None:
            l, t, r, b = _rect(self.target)
            cy = (t + b) / 2
            hole = isinstance(self.target, WallHole)
            edge = l + (r - l) * self.erase
            stand = (l + r) / 2 if hole else edge - 150  # jet reaches ~150 px to his right
            # lance at the middle of the piece: feet that much lower than the hand
            reach = self.feet() - self.hand()[1]
            want = self.floor() - BASE - DECK - (cy + reach)
            if self.phase == "drive":
                at = self.drive_to(stand, dt)
                up = self.lift_to(want, dt)
                if at and up:
                    self.phase, self.f = "wash", 1
            elif self.phase == "wash":
                self.f = 1
                self.drive_to(stand, dt)
                self.lift_to(want, dt)
                self.erase = min(1.0, self.erase + (WASH * dt / max(120.0, r - l) if not hole else dt / 1.4))
                self.aim = (edge if not hole else (l + r) / 2,
                            cy + math.sin(self.t * 8) * (b - t) * (0.3 if not hole else 0.15))
                if hole:
                    if self.erase >= 1.0:
                        self.target.age = max(self.target.age, HOLE_LIFE)  # plastered: it fades from here
                        c.done(self.target, keep=True)
                        self.target, self.erase, self.phase = None, 0.0, "lower"
                else:
                    self.target.erase = self.erase
                    self.target.update()
                    if self.erase >= 1.0:
                        c.done(self.target)
                        c.fx.append(PopText((l + r) / 2, cy, "SCHOON!"))
                        self.target, self.erase, self.phase = None, 0.0, "lower"
                self.say_cd -= dt
                if self.say_cd <= 0:
                    self.say_cd = _rng.uniform(5, 9)
                    c.fx.append(PopText(self.x, self.feet() - 80, _rng.choice(CREW_SAYS)))
        else:
            self.target = c.claim(self)
            if self.target is None:
                self.phase = "leave"
        self.place()
        self.update()
        return True

    # ---- looks
    def paintEvent(self, _):
        qp = _painter(self)
        top = self.top
        fl = self.floor() - top
        fx = WX
        base_top = fl - BASE
        deck = base_top - self.lift - DECK
        # scissor arms
        if self.lift > 2:
            n = max(1, int(self.lift / 34) + 1)
            seg = self.lift / n
            qp.setPen(QPen(QColor(90, 90, 96), 3, Qt.SolidLine, Qt.RoundCap))
            for i in range(n):
                y0, y1 = base_top - i * seg, base_top - (i + 1) * seg
                qp.drawLine(QPointF(fx - 26, y0), QPointF(fx + 26, y1))
                qp.drawLine(QPointF(fx + 26, y0), QPointF(fx - 26, y1))
        # chassis and wheels
        qp.setPen(QPen(QColor(40, 40, 40), 2))
        qp.setBrush(QColor(255, 196, 0))
        qp.drawRoundedRect(QRectF(fx - 36, base_top, 72, BASE - 6), 4, 4)
        qp.setBrush(QColor(30, 30, 30))
        for wx in (fx - 22, fx + 22):
            qp.drawEllipse(QPointF(wx, fl - 6), 6, 6)
            a = self.wheel
            qp.setPen(QPen(QColor(200, 200, 200), 1.5))
            qp.drawLine(QPointF(wx, fl - 6), QPointF(wx + math.cos(a) * 5, fl - 6 + math.sin(a) * 5))
            qp.setPen(QPen(QColor(40, 40, 40), 2))
        qp.setPen(QPen(QColor(20, 20, 20), 1))
        qp.drawText(QRectF(fx - 34, base_top + 1, 68, BASE - 8), Qt.AlignCenter, "GEMEENTE")
        # platform with railing
        qp.setPen(QPen(QColor(40, 40, 40), 2))
        qp.setBrush(QColor(255, 196, 0))
        qp.drawRect(QRectF(fx - 32, deck, 64, DECK))
        qp.setPen(QPen(QColor(255, 196, 0), 3, Qt.SolidLine, Qt.RoundCap))
        qp.drawLine(QPointF(fx - 30, deck), QPointF(fx - 30, deck - 30))
        qp.drawLine(QPointF(fx + 30, deck), QPointF(fx + 30, deck - 30))
        qp.drawLine(QPointF(fx - 30, deck - 30), QPointF(fx + 30, deck - 30))
        # the worker himself
        feet = deck
        pose = self.pose()
        k = self.crew.kit
        k["draw"](qp, fx, feet, pose, self.f, QColor(45, 45, 52), SCALE)
        pts = k["skeleton"](pose, self.f)

        def P(name, dx=0.0, dy=0.0):
            return QPointF(fx + pts[name][0] * SCALE + dx, feet + pts[name][1] * SCALE + dy)

        neck, hip = P("neck"), P("hip")
        vest = QPolygonF([neck + QPointF(-7, 3), neck + QPointF(7, 3), hip + QPointF(6, -2), hip + QPointF(-6, -2)])
        qp.setPen(QPen(QColor(120, 50, 0), 1))
        qp.setBrush(QColor(255, 110, 0))
        qp.drawPolygon(vest)
        qp.setPen(QPen(QColor(235, 240, 245), 2.5))
        for k2 in (0.45, 0.72):
            y = neck.y() + (hip.y() - neck.y()) * k2
            qp.drawLine(QPointF(min(neck.x(), hip.x()) - 6, y), QPointF(max(neck.x(), hip.x()) + 6, y))
        head = P("head")
        r = 10 * SCALE + 3
        qp.setPen(QPen(QColor(60, 50, 0), 1))
        qp.setBrush(QColor(255, 225, 40))
        qp.drawChord(QRectF(head.x() - r, head.y() - r - 2, 2 * r, 2 * r), 0, 180 * 16)
        qp.drawRect(QRectF(head.x() - r - 3, head.y() - 3, 2 * r + 6, 2.5))
        if self.phase == "wash":
            self.paint_jet(qp, P("hand_a"))

    def paint_jet(self, qp, hand):
        tip = hand + QPointF(34, -4)
        qp.setPen(QPen(QColor(60, 60, 70), 4, Qt.SolidLine, Qt.RoundCap))
        qp.drawLine(hand, tip)  # the lance
        ax, ay = self.aim[0] - (self.x - WX), self.aim[1] - self.top
        end = QPointF(min(ax, WIN_W - 6), ay)
        for w, col in ((7, QColor(170, 215, 255, 90)), (3, QColor(235, 248, 255, 220))):
            qp.setPen(QPen(col, w, Qt.SolidLine, Qt.RoundCap))
            qp.drawLine(tip, end)
        qp.setPen(Qt.NoPen)
        for i in range(10):  # spray and foam where it hits
            a = i * 2.4 + self.t * 13
            d = 4 + (i * 7 + self.t * 60) % 22
            qp.setBrush(QColor(255, 255, 255, 200) if i % 3 else QColor(190, 225, 255, 170))
            qp.drawEllipse(end + QPointF(math.cos(a) * d * 0.5 - 6, math.sin(a) * d), 2.5 + i % 3, 2.5 + i % 3)


class Cleanup:
    """Dispatches the crew, keeps track of what's left to clean, and decides when they come by themselves."""

    def __init__(self, dude, kit):
        self.d, self.kit = dude, kit
        self.workers: list[Worker] = []
        self.fx: list = []
        self.claimed: set[int] = set()
        self.cd, self.check = 120.0, 20.0

    @property
    def active(self):
        return bool(self.workers)

    def targets(self):
        d = self.d
        busy = d.vandal.job.get("w") if d.vandal.job.get("kind") == "spray" else None
        out = [g for g in d.terror.graffiti if g is not busy and getattr(g, "fading", None) is None]
        out += [w for w in d.vandal.wall if w is not busy and (isinstance(w, WallPiece)
                or (isinstance(w, WallHole) and not w.patched))]
        return out

    def alive(self, w):
        return w in self.d.terror.graffiti or w in self.d.vandal.wall

    def claim(self, worker):
        left = [w for w in self.targets() if id(w) not in self.claimed]
        if not left:
            return None
        w = min(left, key=lambda g: abs((_rect(g)[0] + _rect(g)[2]) / 2 - worker.x))
        self.claimed.add(id(w))
        return w

    def done(self, w, keep=False):
        self.claimed.discard(id(w))
        if keep:
            return
        if w in self.d.terror.graffiti:
            self.d.terror.graffiti.remove(w)
        if w in self.d.vandal.wall:
            self.d.vandal.wall.remove(w)
        w.kill()

    def start(self, auto=False) -> bool:
        d = self.d
        jobs = self.targets()
        if self.active or not jobs:
            return False
        wd = d.world
        n = min(3, 1 + len(jobs) // 3)
        for i in range(n):
            side = -1 if i % 2 == 0 else 1  # from the left, from the right, from the left
            x = wd.left - 60 - i * 70 if side < 0 else wd.right + 60 + i * 70
            self.workers.append(Worker(self, x, side))
        d.terror.say("crew")
        d.rage = min(1.0, d.rage + 0.15)
        self.cd = 240.0
        return True

    def step(self, dt, cur, btn):
        self.cd -= dt
        self.check -= dt
        if self.workers:
            self.workers = [w for w in self.workers if w.step(dt)]
            if not self.workers:  # all gone: the dude gets the last word
                self.claimed.clear()
                d = self.d
                d.terror.later(1.0, lambda: d.terror.say("crew_gone"))
                if _rng.random() < 0.5:
                    d.terror.later(4.0, lambda: d.terror.trigger("graffiti"))
        elif self.check <= 0:
            self.check = 20.0
            n = len(self.targets())
            if self.cd <= 0 and (n >= 6 or (n >= 3 and _rng.random() < 0.15)):
                self.start(auto=True)
        self.fx = [w for w in self.fx if w.step(dt)]

    def set_visible(self, vis):
        for w in self.workers + self.fx:
            w.setVisible(vis)

    def release(self):
        for w in self.workers + self.fx:
            w.kill()
        self.workers, self.fx = [], []
        self.claimed.clear()

