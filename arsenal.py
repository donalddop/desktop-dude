"""The dude's arsenal: from baseball bats, golf clubs and a raw herring to shotguns and dynamite.

House rules still apply: your cursor gets flung (never while you hold a mouse button), windows
snap back, bullet holes and pie splats fade. Hit or throw him and he drops whatever he's holding.
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainterPath, QPen, QPolygonF

from warfare import OUTLINE, Blast, BulletHole, FxWindow, Tracer, _painter

G = 1500.0
MELEE = ("bat", "golf", "pan", "haring", "chainsaw", "chicken")
GUNS = ("pistol", "mg", "shotgun", "sniper")
THROWN = ("grenade", "dynamite", "pie", "boomerang")
WACKY = ("bat", "golf", "pan", "haring", "chicken", "pie", "boomerang", "pistol")

# melee angles: 0 = down, pi/2 = forward, pi = up (same as his arms); back -> fwd is the swing
WEAPONS = {
    "bat": {"label": "Honkbalknuppel", "kind": "melee", "back": 4.3, "fwd": 1.4, "swing": 0.16, "len": 48,
            "reach": 90, "fling": 520, "elev": 0.3, "height": 60, "dur": 0.35, "text": "HOME RUN!",
            "snd": "bonk", "win": "shake"},
    "golf": {"label": "Golfclub", "kind": "melee", "back": -2.6, "fwd": 2.5, "swing": 0.26, "len": 54,
             "reach": 80, "fling": 700, "elev": 0.6, "height": 280, "dur": 0.8, "text": "FORE!",
             "snd": "bonk", "win": None},
    "pan": {"label": "Koekenpan", "kind": "melee", "back": 3.6, "fwd": 0.9, "swing": 0.14, "len": 40,
            "reach": 80, "fling": 240, "elev": -0.6, "height": 0, "dur": 0.25, "text": "BONK!",
            "snd": "clang", "win": "shake"},
    "haring": {"label": "Haring", "kind": "melee", "back": 3.4, "fwd": 1.0, "swing": 0.15, "len": 42,
               "reach": 80, "fling": 170, "elev": 0.15, "height": 30, "dur": 0.3, "text": "KLETS!",
               "snd": "splat", "win": "shake"},
    "chainsaw": {"label": "Kettingzaag", "kind": "melee", "back": 1.75, "fwd": 1.45, "swing": 0.5, "len": 52,
                 "reach": 95, "fling": 320, "elev": 0.05, "height": 0, "dur": 0.3, "text": "VRRRAAAH!",
                 "snd": "saw", "win": "slice", "hit": 0.4},
    "chicken": {"label": "Rubberen kip", "kind": "melee", "back": 3.5, "fwd": 1.1, "swing": 0.18, "len": 48,
                "reach": 80, "fling": 45, "elev": 0.3, "height": 20, "dur": 0.3, "text": "SQUEAK!",
                "snd": "squeak", "win": None},
    "pistol": {"label": "Pistool", "kind": "gun", "shots": 3, "gap": 0.22, "spread": 20, "push": 70,
               "len": 20, "snd": "shot", "aim": 0.45},
    "mg": {"label": "Machinegeweer", "kind": "gun", "shots": 18, "gap": 0.065, "spread": 40, "push": 28,
           "len": 46, "snd": "shot", "aim": 0.6},
    "shotgun": {"label": "Shotgun", "kind": "gun", "shots": 1, "gap": 0.5, "spread": 60, "pellets": 7,
                "push": 260, "len": 38, "snd": "fire", "aim": 0.55},
    "sniper": {"label": "Sniper", "kind": "gun", "shots": 1, "gap": 0.3, "spread": 0, "push": 450,
               "len": 58, "snd": "fire", "aim": 1.6},
    "grenade": {"label": "Handgranaat", "kind": "throw", "item": "grenade"},
    "dynamite": {"label": "Dynamiet", "kind": "throw", "item": "dynamite"},
    "pie": {"label": "Slagroomtaart", "kind": "throw", "item": "pie"},
    "boomerang": {"label": "Boemerang", "kind": "throw", "item": "boomerang"},
}


# --------------------------------------------------------------------------- drawings
# Weapons are drawn along +x from the hand (x=0); thrown items are drawn centred on (0, 0).


def _pen(qp, col, w):
    qp.setPen(QPen(col, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))


def draw_bat(qp, t):
    qp.setPen(QPen(OUTLINE, 1.5))
    qp.setBrush(QColor(176, 122, 64))
    qp.drawPolygon(QPolygonF([QPointF(-6, -2.5), QPointF(46, -6), QPointF(49, 0), QPointF(46, 6), QPointF(-6, 2.5)]))
    qp.setBrush(QColor(60, 40, 25))
    qp.drawEllipse(QPointF(-7, 0), 3.5, 3.5)


def draw_golf(qp, t):
    _pen(qp, OUTLINE, 4.5)
    qp.drawLine(QPointF(-4, 0), QPointF(52, 0))
    _pen(qp, QColor(175, 180, 190), 2.2)
    qp.drawLine(QPointF(-4, 0), QPointF(52, 0))
    _pen(qp, QColor(25, 25, 25), 4)
    qp.drawLine(QPointF(-4, 0), QPointF(8, 0))
    qp.setPen(QPen(OUTLINE, 1.2))
    qp.setBrush(QColor(60, 60, 70))
    qp.drawRoundedRect(QRectF(50, -1, 8, 12), 2, 2)


def draw_pan(qp, t):
    _pen(qp, QColor(30, 30, 30), 4)
    qp.drawLine(QPointF(-4, 0), QPointF(17, 0))
    qp.setPen(QPen(OUTLINE, 1.5))
    qp.setBrush(QColor(55, 55, 60))
    qp.drawEllipse(QPointF(29, 0), 13, 13)
    qp.setBrush(QColor(95, 95, 102))
    qp.drawEllipse(QPointF(29, 0), 9, 9)


def draw_haring(qp, t):
    qp.setPen(QPen(OUTLINE, 1.2))
    qp.setBrush(QColor(150, 170, 190))
    qp.drawPolygon(QPolygonF([QPointF(-3, -7), QPointF(7, 0), QPointF(-3, 7)]))  # held by the tail
    qp.drawEllipse(QPointF(25, 0), 19, 7)
    qp.setBrush(QColor(20, 20, 20))
    qp.drawEllipse(QPointF(39, -1.5), 1.7, 1.7)
    qp.setPen(QPen(QColor(90, 110, 130), 1))
    qp.drawLine(QPointF(12, 1), QPointF(35, 1))


def draw_chainsaw(qp, t):
    qp.translate(0, math.sin(t * 90) * 0.8)
    qp.setPen(QPen(OUTLINE, 1.5))
    qp.setBrush(QColor(235, 120, 30))
    qp.drawRoundedRect(QRectF(-6, -8, 24, 16), 3, 3)
    qp.setBrush(QColor(170, 175, 180))
    qp.drawRoundedRect(QRectF(18, -4, 34, 8), 4, 4)
    qp.setPen(Qt.NoPen)
    qp.setBrush(QColor(40, 40, 40))
    off = (t * 120) % 6
    for i in range(6):
        x = 19 + i * 6 + off
        if x < 50:
            qp.drawRect(QRectF(x, -6, 2, 2))
            qp.drawRect(QRectF(x, 4, 2, 2))
    _pen(qp, QColor(25, 25, 25), 3)
    qp.drawLine(QPointF(0, -8), QPointF(8, -12))


def draw_chicken(qp, t):
    _pen(qp, QColor(255, 140, 30), 2)
    qp.drawLine(QPointF(3, -2), QPointF(-4, -6))
    qp.drawLine(QPointF(3, 2), QPointF(-4, 6))
    qp.setPen(QPen(OUTLINE, 1.2))
    qp.setBrush(QColor(250, 215, 60))
    qp.drawEllipse(QPointF(22, 0), 19, 5.5)
    qp.drawEllipse(QPointF(41, -2), 5, 5)
    qp.setBrush(QColor(220, 40, 40))
    qp.drawEllipse(QPointF(42, -7.5), 3, 2)
    qp.setBrush(QColor(255, 140, 30))
    qp.drawPolygon(QPolygonF([QPointF(45, -3), QPointF(51, -1), QPointF(45, 1)]))


def draw_pistol(qp, t):
    qp.setPen(QPen(OUTLINE, 1.2))
    qp.setBrush(QColor(30, 30, 35))
    qp.drawRect(QRectF(-2, -5, 22, 6))
    qp.drawRect(QRectF(-2, 0, 7, 9))


def draw_mg(qp, t):
    qp.setPen(QPen(OUTLINE, 1.2))
    qp.setBrush(QColor(35, 38, 30))
    qp.drawRect(QRectF(-14, -5, 40, 9))
    qp.drawRect(QRectF(26, -2, 20, 3))
    qp.setBrush(QColor(70, 70, 60))
    qp.drawEllipse(QPointF(6, 9), 7, 7)


def draw_shotgun(qp, t):
    qp.setPen(QPen(OUTLINE, 1.2))
    qp.setBrush(QColor(120, 70, 35))
    qp.drawPolygon(QPolygonF([QPointF(-16, -3), QPointF(4, -4), QPointF(4, 4), QPointF(-16, 7)]))
    qp.setBrush(QColor(30, 30, 32))
    qp.drawRect(QRectF(4, -4, 34, 5))
    qp.setBrush(QColor(120, 70, 35))
    qp.drawRect(QRectF(14, 1, 10, 4))


def draw_sniper(qp, t):
    qp.setPen(QPen(OUTLINE, 1.2))
    qp.setBrush(QColor(60, 75, 45))
    qp.drawPolygon(QPolygonF([QPointF(-18, -3), QPointF(6, -4), QPointF(6, 4), QPointF(-18, 6)]))
    qp.setBrush(QColor(30, 30, 32))
    qp.drawRect(QRectF(6, -3, 52, 4))
    qp.drawRect(QRectF(6, -10, 20, 5))
    qp.setBrush(QColor(120, 200, 255))
    qp.drawEllipse(QPointF(26, -7.5), 2, 2.5)


def draw_grenade(qp, t):
    qp.setPen(QPen(OUTLINE, 1.5))
    qp.setBrush(QColor(70, 95, 50))
    qp.drawEllipse(QPointF(0, 0), 7, 8)
    _pen(qp, QColor(40, 55, 30), 1.2)
    qp.drawLine(QPointF(-6, 0), QPointF(6, 0))
    qp.setPen(QPen(OUTLINE, 1.2))
    qp.setBrush(QColor(150, 150, 150))
    qp.drawRect(QRectF(-3, -11, 6, 4))
    qp.setBrush(Qt.NoBrush)
    qp.drawEllipse(QPointF(5, -11), 3, 3)


def draw_dynamite(qp, t):
    qp.setPen(QPen(OUTLINE, 1.2))
    qp.setBrush(QColor(200, 40, 35))
    for dx in (-7, 0, 7):
        qp.drawRoundedRect(QRectF(dx - 3.5, -10, 7, 20), 2, 2)
    _pen(qp, QColor(40, 40, 40), 2)
    qp.drawLine(QPointF(-10, -1), QPointF(10, -1))
    _pen(qp, QColor(60, 50, 40), 1.5)
    qp.drawLine(QPointF(0, -10), QPointF(4, -16))
    if int(t * 20) % 2 == 0:
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(255, 220, 80))
        qp.drawEllipse(QPointF(4, -17), 3, 3)


def draw_pie(qp, t):
    qp.setPen(QPen(OUTLINE, 1.2))
    qp.setBrush(QColor(200, 170, 120))
    qp.drawPolygon(QPolygonF([QPointF(-11, 0), QPointF(11, 0), QPointF(8, 6), QPointF(-8, 6)]))
    qp.setBrush(QColor(255, 250, 238))
    qp.drawEllipse(QPointF(0, -1), 12, 5)
    qp.setBrush(QColor(200, 20, 40))
    qp.drawEllipse(QPointF(0, -6), 2.5, 2.5)


def draw_boomerang(qp, t):
    qp.setPen(QPen(OUTLINE, 1.2))
    qp.setBrush(QColor(160, 100, 50))
    qp.drawPolygon(QPolygonF([QPointF(-14, 8), QPointF(0, -8), QPointF(14, 8), QPointF(10, 10),
                              QPointF(0, -2), QPointF(-10, 10)]))


DRAW = {
    "bat": draw_bat, "golf": draw_golf, "pan": draw_pan, "haring": draw_haring, "chainsaw": draw_chainsaw,
    "chicken": draw_chicken, "pistol": draw_pistol, "mg": draw_mg, "shotgun": draw_shotgun,
    "sniper": draw_sniper, "grenade": draw_grenade, "dynamite": draw_dynamite, "pie": draw_pie,
    "boomerang": draw_boomerang,
}


# --------------------------------------------------------------------------- overlays


class PopText(FxWindow):
    """Comic-book text: HOME RUN!, BONK!, KABOEM!"""

    LIFE = 0.9

    def __init__(self, x, y, text):
        font = QFont("Impact")
        font.setPixelSize(42)
        font.setItalic(True)
        super().__init__(QFontMetrics(font).horizontalAdvance(text) + 40, 80)
        self.x, self.y, self.age = x, y, 0.0
        path = QPainterPath()
        path.addText(0, 0, font, text)
        br = path.boundingRect()
        self.path = path.translated(self.w_ / 2 - br.center().x(), self.h_ / 2 - br.center().y())
        self.place_at(x, y)
        self.show()

    def step(self, dt) -> bool:
        self.age += dt
        if self.age >= self.LIFE:
            self.kill()
            return False
        self.place_at(self.x, self.y - 45 * self.age)
        if self.age > self.LIFE - 0.3:
            self.setWindowOpacity(max(0.0, (self.LIFE - self.age) / 0.3))
        self.update()
        return True

    def paintEvent(self, _):
        qp = _painter(self)
        s = min(1.0, 0.4 + self.age / 0.12 * 0.6)
        qp.translate(self.w_ / 2, self.h_ / 2)
        qp.scale(s, s)
        qp.translate(-self.w_ / 2, -self.h_ / 2)
        qp.setPen(QPen(QColor(20, 20, 20), 6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        qp.setBrush(Qt.NoBrush)
        qp.drawPath(self.path)
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(255, 215, 40))
        qp.drawPath(self.path)


class Splat(FxWindow):
    """Whipped cream on your screen. Drips, then fades."""

    LIFE, FADE = 9.0, 2.0

    def __init__(self, x, y):
        super().__init__(140, 140)
        self.place_at(x, y)
        self.age = 0.0
        self.blobs = [(random.uniform(-28, 28), random.uniform(-22, 18), random.uniform(8, 17)) for _ in range(9)]
        self.drips = [(random.uniform(-26, 26), random.uniform(18, 48)) for _ in range(4)]
        self.show()

    def step(self, dt) -> bool:
        self.age += dt
        if self.age >= self.LIFE:
            self.kill()
            return False
        if self.age < 3.0:
            self.update()
        elif self.age > self.LIFE - self.FADE:
            self.setWindowOpacity(max(0.0, (self.LIFE - self.age) / self.FADE))
        return True

    def paintEvent(self, _):
        qp = _painter(self)
        c = 70
        cream = QColor(255, 250, 238)
        grow = min(1.0, self.age / 3.0)
        _pen(qp, QColor(210, 205, 190), 9)
        for dx, ln in self.drips:
            qp.drawLine(QPointF(c + dx, c), QPointF(c + dx, c + 10 + ln * grow))
        _pen(qp, cream, 6)
        for dx, ln in self.drips:
            qp.drawLine(QPointF(c + dx, c), QPointF(c + dx, c + 10 + ln * grow))
        qp.setPen(QPen(QColor(215, 210, 195), 2))
        qp.setBrush(cream)
        for dx, dy, r in self.blobs:
            qp.drawEllipse(QPointF(c + dx, c + dy), r, r)
        qp.setPen(Qt.NoPen)
        for dx, dy, r in self.blobs:
            qp.drawEllipse(QPointF(c + dx, c + dy), r - 1.5, r - 1.5)
        qp.setBrush(QColor(200, 20, 40))
        qp.drawEllipse(QPointF(c + 4, c - 12), 5, 5)


class LaserDot(FxWindow):
    """Sniper's red dot, sitting right on your cursor. Move."""

    def __init__(self):
        super().__init__(30, 30)
        self.t = 0.0
        self.show()

    def paintEvent(self, _):
        qp = _painter(self)
        self.t += 1 / 60
        p = 0.5 + 0.5 * math.sin(self.t * 12)
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(255, 0, 0, int(70 + 60 * p)))
        qp.drawEllipse(QPointF(15, 15), 9 + 3 * p, 9 + 3 * p)
        qp.setBrush(QColor(255, 30, 30))
        qp.drawEllipse(QPointF(15, 15), 3.5, 3.5)


class Thrown(FxWindow):
    """Grenade (bounces, 2s fuse), dynamite (sticks, 3-2-1, big boom) or pie (splats)."""

    def __init__(self, item, x, y, vx, vy):
        super().__init__(110, 110)
        self.item, self.x, self.y, self.vx, self.vy = item, x, y, vx, vy
        self.rot, self.spin = 0.0, (0.0 if item == "pie" else random.uniform(-720, 720))
        self.age, self.count, self.bounces, self.landed = 0.0, 0.0, 0, False
        self.place_at(x, y)
        self.show()

    def step(self, dt, ar) -> bool:
        d = ar.d
        world = d.world
        self.age += dt
        if not self.landed:
            prev_y = self.y
            self.vy += G * dt
            self.x += self.vx * dt
            self.y += self.vy * dt
            self.rot += self.spin * dt
            if not world.left + 8 <= self.x <= world.right - 8:
                self.x = min(max(self.x, world.left + 8), world.right - 8)
                self.vx = -self.vx * 0.5
            ground = world.floor_at(self.x)
            for p in world.plats:
                if p.x1 <= self.x <= p.x2 and prev_y <= p.y <= self.y and p.y < ground:
                    ground = p.y
            if self.item == "pie":
                cur = d.w32.cursor_pos()
                if math.hypot(cur[0] - self.x, cur[1] - self.y) < 30 or self.y >= ground - 6:
                    self.kill()
                    ar.splat(self.x, min(self.y, ground - 6), cur)
                    return False
            if self.y >= ground - 6:
                self.y = ground - 6
                if self.item == "grenade" and self.bounces < 2 and self.vy > 300:
                    self.vy, self.vx, self.bounces = -self.vy * 0.45, self.vx * 0.6, self.bounces + 1
                else:
                    self.landed, self.vx, self.vy, self.spin = True, 0.0, 0.0, 0.0
        if self.item == "grenade" and self.age >= 2.0:
            self.kill()
            d.explode(self.x, self.y)
            return False
        if self.item == "dynamite" and self.landed:
            self.count += dt
            if self.count >= 3.0:
                self.kill()
                ar.big_boom(self.x, self.y)
                return False
        self.place_at(self.x, self.y)
        self.update()
        return True

    def paintEvent(self, _):
        qp = _painter(self)
        qp.translate(55, 55)
        qp.rotate(self.rot)
        DRAW[self.item](qp, self.age)
        if self.item == "dynamite" and self.landed:
            qp.resetTransform()
            f = QFont("Impact")
            f.setPixelSize(34)
            path = QPainterPath()
            path.addText(43, 34, f, str(max(1, 3 - int(self.count))))
            qp.setPen(QPen(QColor(255, 255, 255), 4))
            qp.drawPath(path)
            qp.setPen(Qt.NoPen)
            qp.setBrush(QColor(220, 20, 20))
            qp.drawPath(path)


class Boomerang(FxWindow):
    """Flies out to your cursor on a curve and comes back to him. Hits on the way out and back."""

    T = 1.7

    def __init__(self, x, y, tx, ty):
        super().__init__(70, 70)
        self.s0, self.dx, self.dy = (x, y), tx - x, ty - y
        ln = math.hypot(self.dx, self.dy) or 1.0
        self.nx, self.ny = -self.dy / ln * 90, self.dx / ln * 90
        self.x, self.y, self.px, self.py = x, y, x, y
        self.age, self.rot, self.hits = 0.0, 0.0, set()
        self.place_at(x, y)
        self.show()

    def step(self, dt, ar) -> bool:
        d = ar.d
        self.age += dt
        self.rot += 900 * dt
        u = self.age / self.T
        if u >= 1.0:
            self.kill()
            return False
        back = max(0.0, (u - 0.5) * 2)
        sx = self.s0[0] + (d.x - self.s0[0]) * back
        sy = self.s0[1] + (d.y - 70 - self.s0[1]) * back
        fwd, lat = math.sin(math.pi * u), math.sin(2 * math.pi * u)
        self.px, self.py = self.x, self.y
        self.x, self.y = sx + self.dx * fwd + self.nx * lat, sy + self.dy * fwd + self.ny * lat
        cur = d.w32.cursor_pos()
        leg = 0 if u < 0.5 else 1
        if leg not in self.hits and math.hypot(cur[0] - self.x, cur[1] - self.y) < 34 and not d.w32.buttons_down():
            self.hits.add(leg)
            mx, my = self.x - self.px, self.y - self.py
            m = math.hypot(mx, my) or 1.0
            ar.fling_cursor(cur, mx / m * 170, my / m * 170, 0, 0.2)
            ar.fx.append(PopText(cur[0], cur[1] - 40, "BOING!"))
            d.terror.sfx.play("bonk")
        self.place_at(self.x, self.y)
        self.update()
        return True

    def paintEvent(self, _):
        qp = _painter(self)
        qp.translate(35, 35)
        qp.rotate(self.rot)
        draw_boomerang(qp, self.age)


# --------------------------------------------------------------------------- the arsenal


class Arsenal:
    def __init__(self, dude, pose_cls, slash_cls):
        self.d, self.Pose, self.Slash = dude, pose_cls, slash_cls
        self.enabled = True
        self.w, self.cfg = None, {}
        self.phase, self.pt, self.a, self.recoil = "", 0.0, 0.6, 0.0
        self.hit_done, self.shots_left, self.shot_t = False, 0, 0.0
        self.items: list = []
        self.fx: list = []
        self.fling = None
        self.dot: LaserDot | None = None
        self.cd, self.count = 6.0, 0
        self.stats = {"swings": 0, "hits": 0, "shots": 0, "thrown": 0}

    # ---- choosing and starting
    def pick(self, cur, anything=False):
        d = self.d
        pool = list(WEAPONS) if anything or d.rage >= 0.4 else list(WACKY)
        if not anything:
            life = getattr(d, "life", None)
            if life is not None:
                pool = [w for w in pool if w in life.unlocked()] or pool
            dist = math.hypot(cur[0] - d.x, cur[1] - (d.y - 60))
            if dist < 170:
                pool = [w for w in pool if w in MELEE] or pool
            elif dist > 750:
                pool = [w for w in pool if w in GUNS] or pool
        return random.choice(pool)

    def auto(self, dt, cur, btn):
        d = self.d
        if not self.enabled or self.cd > 0 or btn or d.state != "chase" or not d.on_ground:
            return False
        if random.random() >= (0.2 + 0.8 * d.rage) * dt:
            return False
        return self.start(self.pick(cur))

    def start(self, name) -> bool:
        d = self.d
        if name not in WEAPONS or d.state in ("tanking", "held", "climb", "ragdoll", "getup", "stunned"):
            return False
        self.drop()
        self.w, self.cfg = name, WEAPONS[name]
        self.phase = {"melee": "approach", "gun": "aim", "throw": "windup"}[self.cfg["kind"]]
        self.pt, self.hit_done, self.recoil, self.a = 0.0, False, 0.0, 0.6
        self.shots_left, self.shot_t = self.cfg.get("shots", 0), 0.0
        d.vx = 0.0
        d.set_state("wield", 99.0)
        d.terror.say(name)
        if name == "chainsaw":
            d.terror.sfx.play("saw")
        self.cd = max(1.5, random.uniform(3.0, 6.0) - 2.0 * d.rage)
        self.count += 1
        return True

    def drop(self):
        self.w, self.cfg, self.phase = None, {}, ""
        if self.dot is not None:
            self.dot.kill()
            self.dot = None

    def finish(self):
        d = self.d
        self.drop()
        d.attack_cd = max(d.attack_cd, 0.8)
        if d.state == "wield":
            d.set_state("chase" if random.random() < d.rage else "idle", 3.0 if d.rage else 1.5)

    # ---- per-frame
    def think(self, dt, cur, btn) -> bool:
        d = self.d
        if d.state == "wield":
            if self.w is None:
                d.set_state("idle", 1.0)
                return True
            self.pt += dt
            self.recoil = max(0.0, self.recoil - dt * 6)
            getattr(self, "run_" + self.cfg["kind"])(dt, cur, btn)
            return True
        return d.state == "chase" and self.auto(dt, cur, btn)

    def run_melee(self, dt, cur, btn):
        d, c = self.d, self.cfg
        dx = cur[0] - d.x
        if self.phase == "approach":
            self.a = 0.6
            d.f = 1 if dx >= 0 else -1
            in_reach = abs(dx) <= c["reach"] - 10 and -170 < cur[1] - d.y < 40
            if in_reach and d.on_ground:
                d.vx = 0.0
                self.phase, self.pt = "windup", 0.0
            elif self.pt > 3.0 or btn:
                self.finish()
            else:
                if abs(dx) > c["reach"] - 10:
                    d.walk(math.copysign(320, dx))
                else:
                    d.vx = 0.0
                if cur[1] - d.y < -170:  # cursor is up on a window: go get it
                    d.navigate(cur[0], cur[1] + 60, dt)
            return
        d.vx = 0.0
        if self.phase == "windup":
            k = min(1.0, self.pt / 0.32)
            self.a = 0.6 + (c["back"] - 0.6) * (1 - (1 - k) ** 2)
            if k >= 1.0:
                self.phase, self.pt = "swing", 0.0
        elif self.phase == "swing":
            k = min(1.0, self.pt / c["swing"])
            self.a = c["back"] + (c["fwd"] - c["back"]) * k
            if self.w == "chainsaw":
                self.a += math.sin(self.pt * 70) * 0.05
            if not self.hit_done and k >= c.get("hit", 0.55):
                self.hit_done = True
                self.melee_hit(cur, btn)
            if k >= 1.0:
                self.phase, self.pt = "recover", 0.0
        elif self.pt > 0.45:
            self.finish()

    def melee_hit(self, cur, btn):
        d, c = self.d, self.cfg
        self.stats["swings"] += 1
        hx, hy = d.limb("hand_a")
        ux, uy = math.sin(self.a) * d.f, math.cos(self.a)
        tx, ty = hx + ux * c["len"], hy + uy * c["len"]
        dx, dy = cur[0] - d.x, cur[1] - d.y
        if not btn and -30 < dx * d.f < c["reach"] + 40 and -190 < dy < 50:
            self.stats["hits"] += 1
            power = c["fling"] * (1 + 0.5 * d.rage)
            ex, ey = math.cos(c["elev"]) * d.f, -math.sin(c["elev"])
            self.fling_cursor(cur, ex * power, ey * power, c["height"], c["dur"])
            self.fx.append(PopText(cur[0], cur[1] - 40, c["text"]))
            d.terror.sfx.play(c["snd"])
        else:
            d.terror.sfx.play("squeak" if self.w == "chicken" else "slash")
        win = d.world.window_at(tx, ty)
        if win is not None and c["win"] == "shake":
            d.shaker.shake(win.hwnd)
        elif win is not None and c["win"] == "slice" and d.shaker.slice(win.hwnd, d.f):
            d.add_mark(self.Slash(tx, ty, 0.0))
        if self.w == "chainsaw":
            self.fx.append(Blast(tx, ty, 14, 0.3))

    def run_gun(self, dt, cur, btn):
        d, c = self.d, self.cfg
        d.vx = 0.0
        d.f = 1 if cur[0] >= d.x else -1
        sx, sy = d.limb("shoulder")
        ang = min(max(math.atan2((cur[0] - sx) * d.f, cur[1] - sy), 0.35), math.pi - 0.15)
        self.a += (ang - self.a) * min(1.0, dt * 14)
        if self.phase == "aim":
            if self.w == "sniper":
                if self.dot is None:
                    self.dot = LaserDot()
                self.dot.place_at(*cur)
                self.dot.update()
            if self.pt >= c["aim"]:
                self.phase, self.pt = "fire", 0.0
        elif self.phase == "fire":
            self.shot_t -= dt
            if self.shots_left > 0 and self.shot_t <= 0:
                self.shots_left -= 1
                self.shot_t = c["gap"]
                self.fire(cur, btn)
            elif self.shots_left <= 0 and self.shot_t <= 0:
                self.phase, self.pt = "recover", 0.0
        elif self.pt > 0.4:
            self.finish()

    def fire(self, cur, btn):
        d, c = self.d, self.cfg
        hx, hy = d.limb("hand_a")
        ux, uy = math.sin(self.a) * d.f, math.cos(self.a)
        mx, my = hx + ux * c["len"], hy + uy * c["len"]
        spread = c["spread"]
        if self.w == "mg":
            spread *= 1 + (c["shots"] - self.shots_left) * 0.06
        hit = False
        for _ in range(c.get("pellets", 1)):
            tx, ty = d.world.clamp(cur[0] + random.uniform(-spread, spread), cur[1] + random.uniform(-spread, spread))
            self.fx.append(Tracer(mx, my, tx, ty))
            d.add_mark(BulletHole(tx, ty))
            hit |= math.hypot(tx - cur[0], ty - cur[1]) < 26
        self.fx.append(Blast(mx, my, 16 if c.get("pellets") else 10, 0.12))
        self.stats["shots"] += 1
        self.recoil = 1.0
        d.terror.sfx.play(c["snd"])
        if self.dot is not None:
            self.dot.kill()
            self.dot = None
        if hit and not btn:
            self.stats["hits"] += 1
            dist = math.hypot(cur[0] - mx, cur[1] - my) or 1.0
            p = c["push"]
            self.fling_cursor(cur, (cur[0] - mx) / dist * p, (cur[1] - my) / dist * p, 0, 0.12 if p < 100 else 0.25)
            if self.w in ("sniper", "shotgun"):
                self.fx.append(PopText(cur[0], cur[1] - 40, "HEADSHOT!" if self.w == "sniper" else "BAM!"))

    def run_throw(self, dt, cur, btn):
        d = self.d
        d.vx = 0.0
        d.f = 1 if cur[0] >= d.x else -1
        if self.phase == "windup":
            k = min(1.0, self.pt / 0.4)
            self.a = 1.0 + 2.7 * k
            if k >= 1.0:
                self.let_go(cur)
                self.phase, self.pt = "recover", 0.0
        else:
            self.a = max(1.2, self.a - dt * 12)
            if self.pt > 0.4:
                self.finish()

    def let_go(self, cur):
        d = self.d
        hx, hy = d.limb("hand_a")
        item = self.cfg["item"]
        self.stats["thrown"] += 1
        d.terror.sfx.play("slash")
        if item == "boomerang":
            self.items.append(Boomerang(hx, hy, *cur))
            return
        dx, dy = cur[0] - hx, cur[1] - hy
        t = min(max(math.hypot(dx, dy) / 850, 0.35), 1.1)
        self.items.append(Thrown(item, hx, hy, dx / t, dy / t - 0.5 * G * t))

    # ---- effects
    def fling_cursor(self, start, vx, vy, height, dur):
        d = self.d
        d.shove = None
        if getattr(d, "life", None) is not None:
            d.life.cursor_hit()
        self.fling = [start, d.world.clamp(start[0] + vx, start[1] + vy), 0.0, dur, height]

    def splat(self, x, y, cur):
        d = self.d
        d.add_mark(Splat(x, y))
        d.terror.sfx.play("splat")
        self.fx.append(PopText(x, y - 40, "SPLAT!"))
        if math.hypot(cur[0] - x, cur[1] - y) < 40 and not d.w32.buttons_down():
            self.fling_cursor(cur, random.uniform(-40, 40), 60, 0, 0.3)

    def big_boom(self, x, y):
        d = self.d
        for i in range(5):
            ang = i * math.tau / 5
            r = 0 if i == 0 else 1
            d.explode(*d.world.clamp(x + math.cos(ang) * 70 * r, y - 30 + math.sin(ang) * 50 * r))
        d.terror._start_quake()
        self.fx.append(PopText(x, y - 120, "KABOEM!"))

    def step(self, dt, cur, btn):
        d = self.d
        self.cd -= dt
        if self.w is not None and d.state != "wield":
            self.drop()  # hit him and he drops it
        if self.fling is not None:
            if btn:
                self.fling = None
            else:
                f = self.fling
                f[2] += dt
                k = min(1.0, f[2] / f[3])
                e = 1 - (1 - k) ** 3
                x = f[0][0] + (f[1][0] - f[0][0]) * e
                y = f[0][1] + (f[1][1] - f[0][1]) * e - f[4] * 4 * k * (1 - k)
                d.w32.set_cursor(*d.world.clamp(x, y))
                if k >= 1.0:
                    self.fling = None
        self.items = [i for i in self.items if i.step(dt, self)]
        self.fx = [w for w in self.fx if w.step(dt)]

    # ---- looks
    def pose(self):
        d = self.d
        if d.state != "wield" or self.w is None:
            return None
        kind = self.cfg["kind"]
        if kind == "melee" and self.phase == "approach":
            return None
        a, r = self.a, self.recoil
        if kind == "gun":
            return self.Pose(-0.1 - 0.2 * r, (0.4, -0.35), (0.2, -0.5), (a - 0.15 * r, a - 0.9), (a, a + 0.5))
        legs = ((0.35, -0.3), (0.15, -0.4)) if kind == "melee" else ((0.3, -0.2), (0.1, -0.3))
        return self.Pose(0.15 if a < 2 else -0.1, *legs, (a - 0.5, a - 0.8), (a - 0.1, a - 0.2))

    def paint(self, qp, hx, hy, f):
        if self.w is None:
            return
        kind = self.cfg["kind"]
        if kind == "throw" and self.phase != "windup":
            return  # already in the air
        a = 0.6 if (kind == "melee" and self.phase == "approach") else self.a
        ux, uy = math.sin(a) * f, math.cos(a)
        qp.save()
        qp.translate(hx, hy)
        qp.rotate(math.degrees(math.atan2(uy, ux)))
        if ux < 0:
            qp.scale(1, -1)
        if kind == "gun":
            qp.translate(-6 * self.recoil, 0)
        if kind == "throw":
            qp.translate(7, 0)
        DRAW[self.cfg.get("item", self.w)](qp, self.d.t)
        qp.restore()

    # ---- lifecycle
    def set_visible(self, vis):
        for w in self.items + self.fx + ([self.dot] if self.dot else []):
            w.setVisible(vis)

    def release(self):
        for w in self.items + self.fx:
            w.kill()
        self.items, self.fx, self.fling = [], [], None
        self.drop()
        if self.d.state == "wield":
            self.d.set_state("idle", 1.0)
