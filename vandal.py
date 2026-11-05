"""Vandal: what the dude does to your bare desktop. Only where he can see wallpaper, and all of it temporary.

- Graffiti pieces painted on the wallpaper layer: behind your icons, under every window, like it's on the wall.
- A hole punched in the wallpaper: bricks behind it and a Mokum rat peeking out. He tapes it up later.
- Icon football with a *copy* of one of your icons. The real icon never moves: it hides under a patch of your
  own wallpaper until the copy flies home.

The wallpaper layer is the WorkerW window behind the desktop icons (the Wallpaper Engine trick). Everything on
it is an ordinary window owned by the dude: quit him (or Tray > Clear graffiti) and it's gone. Nothing is ever
written to your real wallpaper or your icon layout.
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QRadialGradient
from PySide6.QtWidgets import QWidget

from arsenal import PopText
from graffiti import Piece, paint_cached, render, text_path
from renderer import Renderer
from terror import LINES, Graffiti, grab
from warfare import FxWindow, _painter

LINES.update({
    "hole": ["Kijk, een Mokumse rat achter je wallpaper!", "Oeps. Muur kapot, mattie", "Was toch al lelijk",
             "Ewa, wie woont daar achter?"],
    "football": ["Effe ballen met je icoontjes", "Pass 'm dan, mattie!", "Dit is mijn Cruijff-moment",
                 "Panna incoming"],
    "goal": ["GOAAAL!", "Panna, tering!", "Ajax-waardig, wollah", "Terug in z'n hok"],
    "wallpiece": ["Nu is je wallpaper pas mooi", "Mokum op je muur, mattie", "Gratis kunst, graag gedaan",
                  "Muurtje claimen"],
    "nicked": ["Hé! Mijn bal!", "Blijf van m'n bal af, sukkel"],
})

WALL_LIFE = 20 * 60.0
OVERLAY_LOW = 0.72  # on top of your windows he stays above this fraction of the screen: the bottom is where you type  # graffiti on the wallpaper fades after 20 minutes
HOLE_LIFE, PATCH_LIFE = 80.0, 25.0
G = 2200.0
_rng = random.Random()  # its own dice: the rest of the dude's behaviour stays exactly as it was


# --------------------------------------------------------------------------- the wallpaper layer
class WallWidget(QWidget):
    """Translucent, click-through widget that lives on the wallpaper layer (behind icons, under windows)."""

    def __init__(self, w32, cx, cy, w, h):
        flags = Qt.FramelessWindowHint | Qt.Tool | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus
        super().__init__(None, flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(int(w), int(h))
        self.w_, self.h_ = int(w), int(h)
        self.left, self.top = round(cx - w / 2), round(cy - h / 2)
        self.rect_ = (self.left, self.top, self.left + self.w_, self.top + self.h_)
        self.age = 0.0
        ox, oy = w32.wall_origin() or (0, 0)
        w32.wall_adopt(int(self.winId()))  # before show: it never flashes on top of your windows
        self.move(self.left - ox, self.top - oy)  # child coordinates of the wallpaper layer
        self.show()

    def kill(self):
        self.close()
        self.deleteLater()


class WallPiece(WallWidget):
    """A graffiti piece on your wallpaper. Sprayed on (by him, live), then it just sits there."""

    def __init__(self, w32, cx, cy, piece: Piece, auto=True):
        w, h = piece.size()
        super().__init__(w32, cx, cy, w, h)
        self.piece, self.auto, self.progress, self.img = piece, auto, 0.0, None

    def set_image(self, img):
        self.img = img
        self.update()

    def set_progress(self, k):
        self.progress = k
        self.update()

    def step(self, dt) -> bool:
        self.age += dt
        if self.auto and self.progress < 1.0:
            self.progress = min(1.0, self.progress + dt / 1.8)
            self.update()
        if self.age > WALL_LIFE:
            self.update()
        if self.age > WALL_LIFE + 3.0:
            self.kill()
            return False
        return True

    def paintEvent(self, _):
        if self.img is None and (self.auto or self.progress >= 1.0):
            self.img = render(self.piece)  # nobody pre-rendered it: do it now (once)
        fade = 1.0 - max(0.0, self.age - WALL_LIFE) / 3.0
        paint_cached(QPainter(self), self.w_, self.h_, self.piece, self.img, self.progress, fade)


class WallHole(WallWidget):
    """A punched hole: torn wallpaper, bricks behind it, cracks, a rat. Gets taped up, then fades."""

    W, H = 240, 210

    def __init__(self, w32, cx, cy, rng=None):
        super().__init__(w32, cx, cy, self.W, self.H)
        rng = rng or _rng
        c = QPointF(self.W / 2, self.H / 2)
        n = 22
        pts = []
        for i in range(n):
            a = i * math.tau / n
            r = rng.uniform(0.7, 1.12)
            pts.append(QPointF(c.x() + math.cos(a) * 62 * r, c.y() + math.sin(a) * 52 * r))
        self.hole = QPolygonF(pts)
        self.cracks = []
        for _ in range(rng.randint(5, 8)):
            p = rng.choice(pts)
            a = math.atan2(p.y() - c.y(), p.x() - c.x())
            line = [p]
            for _k in range(rng.randint(3, 5)):
                a += rng.uniform(-0.6, 0.6)
                q = line[-1]
                step = rng.uniform(8, 16)
                line.append(QPointF(q.x() + math.cos(a) * step, q.y() + math.sin(a) * step))
            self.cracks.append(QPolygonF(line))
        self.flaps = []
        for p in rng.sample(pts, 5):
            a = math.atan2(p.y() - c.y(), p.x() - c.x()) + rng.uniform(-0.3, 0.3)
            ln = rng.uniform(10, 20)
            self.flaps.append(QPolygonF([p + QPointF(-math.sin(a) * 7, math.cos(a) * 7),
                                         p + QPointF(math.cos(a) * ln, math.sin(a) * ln),
                                         p + QPointF(math.sin(a) * 7, -math.cos(a) * 7)]))
        self.bricks = [(rng.randint(-14, 14), rng.randint(-8, 8)) for _ in range(60)]
        self.rat_next, self.rat_up, self.rat_k = rng.uniform(1.0, 2.0), False, 0.0
        self.blink = 0.0
        self.tape = rng.uniform(-0.3, 0.3)
        self.wall_img = self.draw_bricks()

    def draw_bricks(self):
        img = QImage(self.W, self.H, QImage.Format_ARGB32_Premultiplied)
        img.fill(QColor(52, 34, 28))
        qp = QPainter(img)
        bw, bh = 34, 15
        i = 0
        for row in range(self.H // bh + 1):
            off = (row % 2) * bw / 2
            for col in range(-1, self.W // bw + 1):
                jr, jg = self.bricks[i % len(self.bricks)]
                i += 1
                qp.fillRect(QRectF(col * bw + off + 1.5, row * bh + 1.5, bw - 3, bh - 3),
                            QColor(150 + jr, 68 + jg, 48 + jg))
        qp.end()
        return img

    @property
    def patched(self):
        return self.age >= HOLE_LIFE

    def step(self, dt) -> bool:
        self.age += dt
        if self.age >= HOLE_LIFE + PATCH_LIFE:
            self.kill()
            return False
        before = (self.rat_k, self.blink > 0)
        if not self.patched:
            if self.age >= self.rat_next:
                self.rat_up = not self.rat_up
                self.rat_next = self.age + (_rng.uniform(2.0, 4.5) if self.rat_up else _rng.uniform(3, 7))
            self.rat_k = min(1.0, self.rat_k + dt * 3) if self.rat_up else max(0.0, self.rat_k - dt * 4)
            self.blink = 0.15 if _rng.random() < dt * 0.6 else max(0.0, self.blink - dt)
        if self.patched or self.age < 0.1 or (self.rat_k, self.blink > 0) != before:
            self.update()  # only repaint when the rat moves or the patch fades
        return True

    def paintEvent(self, _):
        qp = _painter(self)
        if self.patched:
            qp.setOpacity(max(0.0, 1.0 - (self.age - HOLE_LIFE) / PATCH_LIFE) ** 0.5)
        hole = QPainterPath()
        hole.addPolygon(self.hole)
        hole.closeSubpath()
        # cracks in the wallpaper around it
        qp.setPen(QPen(QColor(25, 20, 18, 190), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for cr in self.cracks:
            qp.drawPolyline(cr)
        # behind the wallpaper: an old brick wall
        qp.save()
        qp.setClipPath(hole)
        qp.drawImage(0, 0, self.wall_img)
        if not self.patched:
            self.paint_rat(qp)
        g = QRadialGradient(QPointF(self.W / 2, self.H / 2), 70)
        g.setColorAt(0.55, QColor(0, 0, 0, 0))
        g.setColorAt(1.0, QColor(0, 0, 0, 200))
        qp.fillRect(self.rect(), g)  # depth: dark towards the torn edge
        qp.restore()
        # torn paper edge and curled flaps
        qp.setBrush(Qt.NoBrush)
        qp.setPen(QPen(QColor(240, 234, 220), 4.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        qp.drawPath(hole)
        qp.setPen(QPen(QColor(120, 110, 95), 1))
        qp.setBrush(QColor(236, 228, 210))
        for f in self.flaps:
            qp.drawPolygon(f)
        if self.patched:
            self.paint_patch(qp, hole)

    def paint_rat(self, qp):
        k = self.rat_k
        if k <= 0.01:
            return
        x, y = self.W / 2 + 6, self.H / 2 + 52 - 46 * k
        qp.setPen(QPen(QColor(30, 25, 25), 1.4))
        qp.setBrush(QColor(232, 160, 170))
        qp.drawEllipse(QPointF(x - 16, y - 16), 8, 8)  # ears
        qp.drawEllipse(QPointF(x + 16, y - 16), 8, 8)
        qp.setBrush(QColor(118, 112, 108))
        qp.drawEllipse(QPointF(x, y), 22, 19)  # head
        qp.drawEllipse(QPointF(x, y + 9), 11, 10)  # snout
        qp.setBrush(QColor(240, 140, 150))
        qp.drawEllipse(QPointF(x, y + 15), 4, 3)  # nose
        qp.setPen(Qt.NoPen)
        for ex in (-8, 8):
            if self.blink > 0:
                qp.setPen(QPen(QColor(15, 15, 15), 2))
                qp.drawLine(QPointF(x + ex - 4, y - 4), QPointF(x + ex + 4, y - 4))
                qp.setPen(Qt.NoPen)
            else:
                qp.setBrush(QColor(15, 15, 15))
                qp.drawEllipse(QPointF(x + ex, y - 4), 4, 4.6)
                qp.setBrush(QColor(255, 255, 255))
                qp.drawEllipse(QPointF(x + ex + 1.3, y - 5.5), 1.4, 1.4)
        qp.setPen(QPen(QColor(230, 230, 230, 200), 1))
        for s in (-1, 1):
            for dy in (-2, 3):
                qp.drawLine(QPointF(x + 7 * s, y + 13), QPointF(x + 28 * s, y + 10 + dy * 2))

    def paint_patch(self, qp, hole):
        """Plaster and two strips of duct tape. 'Niemand merkt het.'"""
        qp.setPen(QPen(QColor(170, 165, 150), 1.5))
        qp.setBrush(QColor(238, 234, 224))
        qp.drawPath(hole)
        qp.save()
        qp.translate(self.W / 2, self.H / 2)
        for a in (35 + self.tape * 20, -35 + self.tape * 20):
            qp.save()
            qp.rotate(a)
            qp.setPen(QPen(QColor(110, 115, 120), 1))
            qp.setBrush(QColor(175, 180, 186))
            qp.drawRect(QRectF(-80, -11, 160, 22))
            qp.restore()
        sig = text_path("niemand merkt het", "marker", 15)
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(20, 20, 20, 210))
        qp.drawPath(sig.translated(0, 42))
        qp.restore()


# --------------------------------------------------------------------------- top-level helpers
class Dust(FxWindow):
    """A cartoon dust cloud: puffs that swell and fade. Takeoff, landing, poof."""

    LIFE = 0.55

    def __init__(self, x, y, big=1.0):
        self.s = int(170 * big)
        super().__init__(self.s, self.s)
        self.place_at(x, y)
        self.age = 0.0
        self.puffs = [(_rng.uniform(-1, 1), _rng.uniform(-0.6, 0.35), _rng.uniform(0.3, 0.55)) for _ in range(9)]
        self.show()

    def step(self, dt) -> bool:
        self.age += dt
        if self.age >= self.LIFE:
            self.kill()
            return False
        self.update()
        return True

    def paintEvent(self, _):
        qp = _painter(self)
        k = self.age / self.LIFE
        s = self.s
        a = int(215 * (1 - k) ** 1.4)
        qp.setPen(QPen(QColor(120, 105, 90, a), 1.5))
        qp.setBrush(QColor(214, 200, 178, a))
        spread = 0.25 + 0.75 * (1 - (1 - k) ** 3)
        for dx, dy, r in self.puffs:
            rad = s * 0.5 * r * (0.45 + 0.7 * spread)
            qp.drawEllipse(QPointF(s / 2 + dx * s * 0.3 * spread, s * 0.62 + dy * s * 0.35 * spread), rad, rad * 0.8)



class Patch(FxWindow):
    """Covers the real icon with your own wallpaper while its copy is out playing."""

    def __init__(self, l, t, w, h, img: QImage | None, colour: QColor):
        super().__init__(int(w), int(h))
        self.move(int(l), int(t))
        self.pm = QPixmap.fromImage(img) if img is not None and not img.isNull() else None
        self.colour = colour
        self.show()

    def paintEvent(self, _):
        qp = _painter(self)
        if self.pm is not None:
            qp.drawPixmap(0, 0, self.pm)
        else:
            qp.fillRect(self.rect(), self.colour)


class Ball(FxWindow):
    """The icon copy, spinning. Click it to give it a boot yourself."""

    def __init__(self, pm: QPixmap, on_click=None):
        d = int(math.hypot(pm.width(), pm.height())) + 6
        super().__init__(d, d, clickable=True)
        self.pm, self.angle, self.on_click = pm, 0.0, on_click
        self.r = min(pm.width(), pm.height()) * 0.42
        self.show()

    def mousePressEvent(self, e):
        if self.on_click is not None and e.button() == Qt.LeftButton:
            self.on_click()

    def paintEvent(self, _):
        qp = _painter(self)
        qp.translate(self.w_ / 2, self.h_ / 2)
        qp.rotate(self.angle)
        qp.drawPixmap(int(-self.pm.width() / 2), int(-self.pm.height() / 2), self.pm)


def cut_out(icon: QImage, wall: QImage | None) -> QImage:
    """The icon without its background: pixels that match the wallpaper underneath become transparent."""
    img = icon.convertToFormat(QImage.Format_ARGB32)
    if wall is None or wall.isNull() or wall.size() != img.size():
        return img
    wall = wall.convertToFormat(QImage.Format_ARGB32)
    for y in range(img.height()):
        for x in range(img.width()):
            a, b = img.pixelColor(x, y), wall.pixelColor(x, y)
            diff = abs(a.red() - b.red()) + abs(a.green() - b.green()) + abs(a.blue() - b.blue())
            if diff < 30:
                img.setPixelColor(x, y, QColor(0, 0, 0, 0))
            elif diff < 70:
                a.setAlpha(int(255 * (diff - 30) / 40))
                img.setPixelColor(x, y, a)
    return img


# --------------------------------------------------------------------------- the vandal
class Vandal:
    KINDS = ("piece", "hole", "football")

    def __init__(self, dude, kit, real=False):
        self.d, self.kit = dude, kit
        self.renderer = Renderer(real)
        if real:
            QTimer.singleShot(3000, self.warm_up)
        self.wall: list = []  # pieces and holes on the wallpaper layer
        self.fx: list = []  # ball, patch, pop texts (top-level)
        self.job: dict = {}
        self.cd = _rng.uniform(45, 90)
        self.enabled = True
        self.last_cur = None
        self.land_watch = 0.0  # after a spray job: puff of dust when he lands

    def warm_up(self):
        """Load the fonts and start the graffiti helper now, not in the middle of his first spray."""
        Piece("tag", scale=0.5)
        self.renderer.start()

    @property
    def FROZEN(self):
        j = self.job
        if self.d.state == "vandal" and j.get("kind") == "spray" and j.get("phase") in ("fly", "spray"):
            return ("vandal",)  # he's up in the air on his own steam, no gravity
        return ()

    # ---- where is there bare wallpaper?
    def wall_ok(self):
        return self.d.w32.wall_origin() is not None

    def free(self, l, t, r, b):
        w = self.d.world
        scr = next((s for s in w.screens if s[0] <= l and r <= s[2] and s[1] <= t and b <= s[3]), None)
        if scr is None:
            return False
        for win in w.wins:
            wl, wt, wr, wb = win.rect
            if l < wr + 4 and wl - 4 < r and t < wb + 4 and wt - 4 < b:
                return False
        return True

    def overlaps_wall(self, l, t, r, b):
        for x in self.wall:
            xl, xt, xr, xb = x.rect_
            if l < xr - 30 and xl + 30 < r and t < xb - 30 and xt + 30 < b:
                return True
        return False

    def spot_for(self, w, h, rng=None):
        """A free place for a w x h thing on the screen he's on, preferably in the upper half."""
        rng = rng or _rng
        rng = rng or _rng
        s = self.d.world.screen_at(self.d.x)
        x1, y1, x2, floor = s[0], s[1], s[2], s[4]
        if x2 - x1 < w + 20 or floor - y1 < h + 20:
            return None
        for _ in range(80):
            cx = rng.uniform(x1 + w / 2 + 10, x2 - w / 2 - 10)
            cy = rng.uniform(y1 + h / 2 + 10, floor - h / 2 - 10)  # anywhere on bare wallpaper, high or low
            box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            if self.free(*box) and not self.overlaps_wall(*box):
                return cx, cy
        return None

    # ---- starting
    def start(self, kind) -> bool:
        d = self.d
        if kind not in self.KINDS or self.job or d.state in ("held", "ragdoll", "tanking", "binned", "aqua"):
            return False
        if not self.wall_ok() and kind == "hole":
            return False
        ok = getattr(self, "start_" + kind)()
        if ok:
            self.cd = _rng.uniform(70, 160)
        return ok

    def start_piece(self, piece: Piece | None = None) -> bool:
        return self.start_spray(piece)

    def start_spray(self, piece: Piece | None = None) -> bool:
        """He jumps up to the spot in a cloud of dust and sprays the piece on live, left to right, then drops.
        On bare wallpaper if there's any (behind your icons), else on top of the screen, high up."""
        d = self.d
        if self.job or d.state in ("held", "ragdoll", "tanking", "binned", "aqua", "climb"):
            return False
        spot, on_wall = None, False
        if self.wall_ok():
            style = _rng.choice(("throwup", "piece", "piece", "tag"))
            scale = _rng.uniform(0.6, 1.8)
            tries = [piece] if piece is not None else [Piece(style, scale=s) for s in (scale, scale * 0.7, 0.6)]
            for wp in tries:  # too big for the bare bit of wallpaper? try it smaller first
                spot = self.spot_for(*wp.size())
                if spot is not None:
                    piece, on_wall = wp, True
                    break
        if spot is None:
            if len(d.terror.graffiti) >= 15:
                return False
            piece = Piece(_rng.choice(("tag", "throwup", "throwup", "piece")), scale=_rng.uniform(0.5, 1.25))
            w, h = piece.size()
            s = d.world.screen_at(d.x)
            # any height, but out of the bottom strip where you type
            x = _rng.uniform(s[0] + w / 2 + 20, s[2] - w / 2 - 20) if s[2] - s[0] > w + 40 else (s[0] + s[2]) / 2
            lo = s[1] + h / 2 + 15
            spot = (x, _rng.uniform(lo, max(lo, s[1] + (s[4] - s[1]) * OVERLAY_LOW - h / 2)))
        if on_wall:
            widget = WallPiece(d.w32, spot[0], spot[1], piece, auto=False)
            self.wall.append(widget)
        else:
            widget = Graffiti(spot[0], spot[1], piece, auto=False)
            d.terror.graffiti.append(widget)
        self.job = {"kind": "spray", "phase": "crouch", "t": 0.0, "piece": piece, "w": widget, "wall": on_wall,
                    "cx": spot[0], "cy": spot[1], "ticket": self.renderer.request(piece), "wait": 0.0}
        d.vx = 0.0
        d.f = 1 if spot[0] >= d.x else -1
        d.set_state("vandal", 99.0)
        return True

    def start_hole(self) -> bool:
        d = self.d
        if not (d.on_ground and d.plat_hwnd is None):
            return False
        y = d.y - WallHole.H / 2  # bottom of the hole at his feet, his fist lands in the middle
        hw, hh = WallHole.W / 2, WallHole.H / 2
        for k in sorted(range(-14, 15), key=abs):
            x = d.x + k * 55
            if self.free(x - hw, y - hh, x + hw, y + hh) and not self.overlaps_wall(x - hw, y - hh, x + hw, y + hh):
                self.job = {"kind": "hole", "phase": "go", "t": 0.0, "x": x, "y": y, "hit": False}
                d.set_state("vandal", 99.0)
                return True
        return False

    def start_football(self) -> bool:
        d = self.d
        icons = d.terror.visible_icons()
        if not icons:
            d.terror.probe.request("icons")
            return False
        if not (d.on_ground and d.plat_hwnd is None):
            return False
        _name, (l, t, r, b) = _rng.choice(icons)
        w, h = r - l, b - t
        shot = grab(l, t, w, h).toImage()
        wall = d.w32.wallpaper_grab(l, t, w, h)
        ring = grab(l - 3, t - 3, w + 6, h + 6).toImage()
        bg = ring.pixelColor(1, 1) if not ring.isNull() else QColor(0, 0, 0)
        img = cut_out(shot, wall)
        patch = Patch(l, t, w, h, wall, bg)
        cx, cy = (l + r) / 2, (t + b) / 2
        ball = Ball(QPixmap.fromImage(img), on_click=self.user_kick)
        ball.place_at(cx, cy)
        self.fx += [patch, ball]
        tx = d.x + d.f * 90
        self.job = {"kind": "football", "phase": "play", "t": 0.0, "home": (cx, cy), "ball": ball, "patch": patch,
                    "bx": cx, "by": cy, "vx": (tx - cx) / 1.1, "vy": -380.0, "spin": 0.0, "kicks": 0,
                    "need": _rng.randint(4, 6), "kick": None}
        d.set_state("vandal", 99.0)
        d.terror.sfx.play("yoink")
        d.terror.say("football")
        return True

    # ---- per frame
    def think(self, dt, cur, btn) -> bool:
        d = self.d
        if d.state == "vandal":
            if not self.job:
                d.set_state("idle", 1.0)
            else:
                getattr(self, "run_" + self.job["kind"])(dt, cur, btn)
            return True
        if (self.enabled and d.terror.enabled and self.cd <= 0 and not btn and d.on_ground and d.plat_hwnd is None
                and d.state in ("idle", "wander") and d.life.duel is None and not d.terror.busy()
                and _rng.random() < 0.05 * dt):
            self.cd = _rng.uniform(40, 90)  # try again later if nothing fits right now
            w = {"hole": 1 + 2 * d.rage, "football": 2.5, "piece": 1.0}
            for kind in self._order(w):
                if self.start(kind):
                    return True
        return False

    @staticmethod
    def _order(weights):
        left = dict(weights)
        out = []
        while left:
            k = _rng.choices(list(left), weights=list(left.values()))[0]
            out.append(k)
            del left[k]
        return out

    def step(self, dt, cur, btn):
        self.cd -= dt
        self.wall = [w for w in self.wall if w.step(dt)]
        self.fx = [w for w in self.fx if not hasattr(w, "step") or w.step(dt)]
        d = self.d
        if self.land_watch > 0:
            self.land_watch -= dt
            if d.on_ground:
                self.land_watch = 0.0
                self.fx.append(Dust(d.x, d.y - 30, 0.75))
                d.terror.sfx.play("bonk")
        j = self.job
        if j.get("kind") == "spray" and d.state != "vandal":  # grabbed mid-spray: the paint finishes itself
            j["w"].auto = True
            self.job = {}
            return
        if j.get("kind") == "football":
            self.ball_physics(dt, cur)
            if self.d.state != "vandal" and j.get("phase") != "home":  # he got grabbed / thrown: ball goes home
                self.send_home()
        elif j and self.d.state != "vandal":
            self.job = {}
        self.last_cur = cur

    # ---- spraying
    SPRAY_POSE_T = 0.3

    def hand_offset(self, pose):
        d = self.d
        hx, hy = d.limb("hand_a", pose)
        return hx - d.x, hy - d.y

    def spray_target(self, k, t):
        """Where his hand goes: on the spray edge, swinging up and down over the letters."""
        j = self.job
        p = j["piece"]
        lx = p.reveal_x(k)
        ly = math.sin(t * 17) * p.half_h * 0.55
        a = math.radians(p.angle)
        return j["cx"] + lx * math.cos(a) - ly * math.sin(a), j["cy"] + lx * math.sin(a) + ly * math.cos(a)

    def run_spray(self, dt, cur, btn):
        d, j = self.d, self.job
        j["t"] += dt
        if j["phase"] == "crouch":
            d.vx = 0.0
            if j["t"] >= 0.16:
                d.f = 1  # he sprays left to right
                ox, oy = self.hand_offset(self.kit["pose_spray"](d.t))
                tx, ty = self.spray_target(0.0, 0.0)
                j.update(phase="fly", t=0.0, sx=d.x, sy=d.y, ex=tx - ox, ey=ty - oy)
                self.fx.append(Dust(d.x, d.y - 25, 1.0))
                d.on_ground, d.plat_hwnd, d.vx, d.vy = False, None, 0.0, 0.0
                d.terror.sfx.play("yoink")
            return
        if j["phase"] == "fly":
            k = min(1.0, j["t"] / 0.42)
            e = k * k * (3 - 2 * k)
            d.x = j["sx"] + (j["ex"] - j["sx"]) * e
            d.y = j["sy"] + (j["ey"] - j["sy"]) * e - 150 * math.sin(math.pi * k)
            d.f = 1 if j["ex"] >= j["sx"] else -1
            if k >= 1.0:
                j.update(phase="spray", t=0.0)
                d.f = 1
                d.terror.sfx.play("spray")
            return
        p = j["piece"]
        if j["w"].img is None:  # the helper is still painting it: hover, shake the can
            img = self.renderer.poll(j["ticket"])
            j["wait"] += dt
            if img is None and (j["ticket"] is None or j["wait"] > 2.5):
                img = render(p)  # no helper (or it's stuck): draw it here, once
            if img is None:
                j["t"] = 0.0
                d.vx = d.vy = 0.0
                return
            j["w"].set_image(img)
        dur = 1.0 + 0.3 * p.scale
        k = min(1.0, j["t"] / dur)
        j["w"].set_progress(k)
        ox, oy = self.hand_offset(self.kit["pose_spray"](d.t))
        tx, ty = self.spray_target(k, j["t"])
        wd = d.world
        d.x = min(max(tx - ox, wd.left + 10), wd.right - 10)
        d.y = min(max(ty - oy, wd.top + 60), wd.bottom - 5)
        d.vx = d.vy = 0.0
        if k >= 1.0:
            j["w"].set_progress(1.0)
            self.fx.append(Dust(d.x, d.y - 50, 0.9))
            d.terror.later(0.4, lambda: d.terror.say("wallpiece" if j["wall"] else "graffiti"))
            self.job = {}
            d.on_ground, d.vx, d.vy = False, 0.0, -220.0
            d.set_state("idle", 1.0)
            self.land_watch = 4.0

    # ---- the hole
    def run_hole(self, dt, cur, btn):
        d, j = self.d, self.job
        j["t"] += dt
        if j["phase"] == "go":
            side = -1 if j["x"] >= d.x else 1
            stand = j["x"] + side * 58
            dx = stand - d.x
            if abs(dx) < 10 or j["t"] > 8:
                d.vx = 0.0
                d.f = 1 if j["x"] >= d.x else -1
                j.update(phase="punch", t=0.0)
            else:
                d.f = 1 if dx > 0 else -1
                d.walk(math.copysign(330, dx))
            return
        d.vx = 0.0
        if j["phase"] == "punch":
            if j["t"] >= 0.22 and not j["hit"]:
                j["hit"] = True
                self.wall.append(WallHole(d.w32, j["x"], j["y"]))
                self.fx.append(PopText(j["x"], j["y"] - 70, "KRAK!"))
                d.terror.sfx.play("bonk")
                d.terror.later(1.0, lambda: d.terror.say("hole"))
                d.rage = max(0.0, d.rage - 0.25)
            if j["t"] >= 0.6:
                j.update(phase="look", t=0.0)
        elif j["phase"] == "look" and j["t"] >= 1.4:
            self.job = {}
            d.set_state("taunt", 1.2)

    # ---- football
    def floor(self, x, r):
        return self.d.world.floor_at(x) - r

    def ball_physics(self, dt, cur):
        j, wd = self.job, self.d.world
        ball = j["ball"]
        if j["phase"] == "home":
            j["t"] += dt
            k = min(1.0, j["t"] / 0.9)
            (x0, y0), (x1, y1) = j["from"], j["home"]
            x = x0 + (x1 - x0) * k
            y = y0 + (y1 - y0) * k - 160 * math.sin(math.pi * k)
            ball.angle += 900 * dt
            ball.place_at(x, y)
            ball.update()
            if k >= 1.0:
                self.fx.append(PopText(x1, y1 - 30, "GOAL!"))
                self.end_football()
            return
        r = ball.r
        j["vy"] += G * dt
        j["bx"] += j["vx"] * dt
        j["by"] += j["vy"] * dt
        fl = self.floor(j["bx"], r)
        if j["by"] >= fl:
            j["by"] = fl
            if j["vy"] > 140:
                j["vy"] = -j["vy"] * 0.55
                if j["vy"] < -500:
                    self.d.terror.sfx.play("bonk")
            else:
                j["vy"] = 0.0
            j["vx"] *= max(0.0, 1 - 1.8 * dt)
            j["spin"] = math.degrees(j["vx"] / max(8.0, r))
        if j["bx"] < wd.left + r:
            j["bx"], j["vx"] = wd.left + r, abs(j["vx"]) * 0.7
        elif j["bx"] > wd.right - r:
            j["bx"], j["vx"] = wd.right - r, -abs(j["vx"]) * 0.7
        if j["by"] < wd.top + r:
            j["by"], j["vy"] = wd.top + r, abs(j["vy"]) * 0.5
        # your cursor can nick it
        if self.last_cur is not None and dt > 0:
            cvx, cvy = (cur[0] - self.last_cur[0]) / dt, (cur[1] - self.last_cur[1]) / dt
            if math.hypot(cur[0] - j["bx"], cur[1] - j["by"]) < r + 14 and math.hypot(cvx, cvy) > 500:
                j["vx"] += cvx * 0.45
                j["vy"] += cvy * 0.45 - 150
                if self.d.state == "vandal":
                    self.d.terror.say("nicked")
        ball.angle += j["spin"] * dt
        ball.place_at(j["bx"], j["by"])
        ball.update()
        patch = j["patch"]
        hx, hy = j["home"]
        patch.setVisible(self.d.world.window_at(hx, hy) is None)  # a window over the icon: no patch needed

    def user_kick(self):
        j = self.job
        if j.get("kind") == "football" and j.get("phase") == "play":
            j["vx"] += _rng.choice((-1, 1)) * _rng.uniform(400, 700)
            j["vy"] = -_rng.uniform(500, 800)
            self.d.terror.say("nicked")

    def run_football(self, dt, cur, btn):
        d, j = self.d, self.job
        if j["phase"] == "home":
            d.vx = 0.0
            return
        j["t"] += dt
        r = j["ball"].r
        on_floor = j["by"] >= self.floor(j["bx"], r) - 40
        if j["kick"] is not None:
            d.vx = 0.0
            j["kick"] += dt
            k = j["kick"] / 0.42
            if k >= 0.45 and not j.get("kicked"):
                j["kicked"] = True
                if abs(j["bx"] - d.x) < 80 and on_floor:
                    j["kicks"] += 1
                    if j["kicks"] >= j["need"]:
                        self.send_home()
                        d.terror.say("goal")
                        return
                    j["vx"] = d.f * _rng.uniform(650, 1100)
                    j["vy"] = -_rng.uniform(350, 850)
                    self.fx.append(PopText(j["bx"], j["by"] - 30, _rng.choice(("PANG!", "BAM!", "TOK!"))))
                    d.terror.sfx.play("bonk")
            if k >= 1.0:
                j["kick"] = None
            return
        if j["t"] > 30:
            self.send_home()
            return
        s = d.world.screen_at(j["bx"])
        kick_dir = 1 if j["bx"] < (s[0] + s[2]) / 2 else -1  # always kick towards the open space
        stand = j["bx"] - kick_dir * 42
        dx = stand - d.x
        if abs(dx) < 16 and on_floor and abs(j["vx"]) < 450:
            d.vx = 0.0
            d.f = kick_dir
            j["kick"], j["kicked"] = 0.0, False
        elif abs(dx) > 6:
            d.f = 1 if dx > 0 else -1
            d.walk(math.copysign(380 if abs(dx) > 60 else 200, dx))
            if d.on_ground and j["by"] < d.y - 160 and abs(j["bx"] - d.x) < 120 and j["vy"] > 0:
                d.jump(-900)  # header attempt
        else:
            d.vx = 0.0

    def send_home(self):
        j = self.job
        if j.get("kind") != "football" or j.get("phase") == "home":
            return
        j.update(phase="home", t=0.0, **{"from": (j["bx"], j["by"])})

    def end_football(self):
        j = self.job
        for k in ("ball", "patch"):
            w = j.get(k)
            if w is not None:
                w.kill()
                if w in self.fx:
                    self.fx.remove(w)
        self.job = {}
        if self.d.state == "vandal":
            self.d.set_state("taunt", 1.2)

    # ---- looks
    def pose(self):
        d, j = self.d, self.job
        if d.state != "vandal" or not j:
            return None
        if j["kind"] == "spray":
            if j["phase"] == "crouch":
                return self.kit["pose_crouch"]()
            if j["phase"] == "fly":
                return self.kit["pose_air"](-600 if j["t"] < 0.21 else 300, d.t)
            return self.kit["pose_spray"](d.t)
        if j["kind"] == "hole" and j["phase"] == "punch":
            return self.kit["pose_punch"](min(1.0, j["t"] / 0.3))
        if j["kind"] == "football" and j.get("kick") is not None:
            return self.kit["pose_kick"](min(1.0, j["kick"] / 0.42))
        return None

    def paint(self, qp, ox, oy, pose, f):
        """His spray can and the paint mist, in the colour of the piece."""
        j = self.job
        if self.d.state != "vandal" or j.get("kind") != "spray" or j.get("phase") != "spray":
            return
        hx, hy = self.kit["skeleton"](pose, f)["hand_a"]
        hx, hy = ox + hx, oy + hy
        qp.setPen(QPen(QColor(255, 255, 255, 190), 1.5))
        qp.setBrush(QColor(200, 40, 60))
        qp.drawRoundedRect(QRectF(hx - 4, hy - 9, 8, 15), 2, 2)
        col = j["piece"].main_colour()
        qp.setPen(Qt.NoPen)
        t = self.d.t
        for i in range(9):
            k = (t * 4 + i / 9) % 1.0
            c = QColor(col)
            c.setAlpha(int(210 * (1 - k)))
            qp.setBrush(c)
            r = 2 + k * 7
            qp.drawEllipse(QPointF(hx + f * (8 + k * 30), hy - 6 + math.sin(i * 7.1) * k * 16), r, r)

    # ---- lifecycle
    def set_visible(self, vis):
        for w in self.fx + self.wall:
            w.setVisible(vis)

    def release(self):
        """Stop what he's doing (the ball pops home right away). What's on the wallpaper stays."""
        j = self.job
        if j.get("kind") == "football":
            self.end_football()
        if j.get("kind") == "spray":
            j["w"].auto = True  # the paint finishes itself
        for w in self.fx:
            w.kill()
        self.fx, self.job = [], {}
        if self.d.state == "vandal":
            self.d.set_state("idle", 1.0)

    def stop(self):
        self.renderer.stop()

    def clear(self):
        """Tray > Clear graffiti: the wallpaper goes back to normal."""
        for w in self.wall:
            w.kill()
        self.wall = []
