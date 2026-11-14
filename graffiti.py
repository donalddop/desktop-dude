"""Graffiti the way it looks on a Mokum wall: tags, throw-ups and pieces.

- tag: fast handstyle (Sedgwick Ave Display / Permanent Marker), one colour, slanted, underline swoosh, a drip.
- throwup: bubble letters (Rubik Bubbles), fat black outline, 3D drop, gradient fill, shine, drips.
- piece: handstyle letters on a cloud, outline, 3D drop, gradient, stars, crown, XXX, signature.

Fonts are bundled from Google Fonts (OFL / Apache 2.0, licenses in assets/fonts). Pure painting: a Piece knows
its size and paints itself at a progress 0..1 (the spray-on reveal), so it works on any widget.
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QTransform,
)

BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
FONT_FILES = {"hand": "SedgwickAveDisplay-Regular.ttf", "bubble": "RubikBubbles-Regular.ttf",
              "marker": "PermanentMarker-Regular.ttf"}
FALLBACK = {"hand": "Segoe Script", "bubble": "Arial Black", "marker": "Impact"}
_families: dict[str, str] = {}

THROWUPS = ["MOKUM", "020", "DUDE", "EWA", "BOEF", "SKEER", "FISSA", "LEIP", "OSSO", "MAZZEL", "TERING",
            "WOLLAH", "KAPOT", "XXX", "DOP"]
TAGS = ["dude020", "mokum kids", "los mokumos", "grand theft fiets", "skate or die", "leip mattie",
        "020 4 life", "west side 020", "fietsdief", "kraakpand", "bitterbal gang", "dude was hier",
        "zwakke cursor", "boefjes", "mazzel"]
PIECES = ["MOKUM", "DUDE", "020", "LOS MOKUMOS", "AMSTERDAM", "BOEF", "FISSA", "SKATE"]
SIGNS = ["dude 020", "d00d", "dude xxx", "dude '26", "mokum kids", "lmk crew"]

# (fill top, fill bottom, 3D drop, overspray) - chrome, Ajax red, toxic, sunset, candy, oranje
PALETTES = [
    ((240, 242, 248), (140, 148, 168), (25, 45, 140), (80, 140, 255)),
    ((235, 35, 50), (140, 10, 25), (20, 20, 20), (255, 255, 255)),
    ((150, 255, 70), (20, 150, 60), (60, 0, 90), (120, 255, 120)),
    ((255, 215, 50), (255, 80, 35), (90, 20, 10), (255, 160, 40)),
    ((255, 110, 210), (140, 50, 230), (25, 20, 70), (255, 120, 255)),
    ((255, 150, 20), (220, 75, 0), (15, 15, 15), (255, 180, 60)),
]
TAG_COLOURS = [(15, 15, 15), (235, 35, 50), (40, 90, 255), (255, 255, 255), (120, 255, 70), (255, 150, 20),
               (255, 80, 200)]


def family(kind: str) -> str:
    if not _families:
        for k, f in FONT_FILES.items():
            fid = QFontDatabase.addApplicationFont(str(BASE / "assets" / "fonts" / f))
            fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
            _families[k] = fams[0] if fams else FALLBACK[k]
    return _families.get(kind, FALLBACK.get(kind, "Impact"))


def text_path(text: str, kind: str, px: int) -> QPainterPath:
    font = QFont(family(kind))
    font.setPixelSize(px)
    if kind == "marker":
        font.setWeight(QFont.Bold)
    p = QPainterPath()
    p.addText(0, 0, font, text)
    br = p.boundingRect()
    return p.translated(-br.center().x(), -br.center().y())


def _c(rgb, a=255):
    return QColor(rgb[0], rgb[1], rgb[2], a)


def _star(qp, x, y, r, col):
    qp.setPen(Qt.NoPen)
    qp.setBrush(col)
    pts = []
    for i in range(8):
        ang = i * math.pi / 4
        rr = r if i % 2 == 0 else r * 0.22
        pts.append(QPointF(x + math.cos(ang) * rr, y + math.sin(ang) * rr))
    qp.drawPolygon(QPolygonF(pts))


def _crown(qp, x, y, s, col, outline=True):
    poly = QPolygonF([QPointF(x - 18 * s, y + 10 * s), QPointF(x - 20 * s, y - 10 * s), QPointF(x - 9 * s, y),
                      QPointF(x, y - 16 * s), QPointF(x + 9 * s, y), QPointF(x + 20 * s, y - 10 * s),
                      QPointF(x + 18 * s, y + 10 * s)])
    qp.setPen(QPen(QColor(10, 10, 10), 3 * s, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin) if outline else Qt.NoPen)
    qp.setBrush(col)
    qp.drawPolygon(poly)


def _xxx(qp, x, y, s):
    """Amsterdam's three St. Andrew's crosses, black on a red bar."""
    qp.setPen(Qt.NoPen)
    qp.setBrush(QColor(210, 25, 40))
    qp.drawRect(QRectF(x - 34 * s, y - 10 * s, 68 * s, 20 * s))
    qp.setPen(QPen(QColor(10, 10, 10), 4.5 * s, Qt.SolidLine, Qt.FlatCap))
    for i in (-1, 0, 1):
        cx = x + i * 22 * s
        qp.drawLine(QPointF(cx - 6 * s, y - 7 * s), QPointF(cx + 6 * s, y + 7 * s))
        qp.drawLine(QPointF(cx + 6 * s, y - 7 * s), QPointF(cx - 6 * s, y + 7 * s))


def _drips(rng, path: QPainterPath, n, maxlen):
    br = path.boundingRect()
    out = []
    for _ in range(n):
        x = rng.uniform(br.left() + br.width() * 0.08, br.right() - br.width() * 0.08)
        # start where the letter really ends: walk up from below until we're inside the shape
        y = br.bottom()
        while y > br.top() and not path.contains(QPointF(x, y)):
            y -= 2
        if y > br.top() + br.height() * 0.4:
            out.append((x, y - 2, rng.uniform(maxlen * 0.3, maxlen), rng.uniform(2.0, 3.6)))
    return out


class Piece:
    """One graffiti piece. Coordinates: centred on (0, 0); size() is the box it needs."""

    def __init__(self, style: str | None = None, text: str | None = None, scale: float = 1.0, rng=None,
                 seed: int | None = None):
        if rng is None:  # seeded: the graffiti helper process can rebuild exactly this piece
            seed = random.randrange(2**31) if seed is None else seed
            rng = random.Random(seed)
        self.seed = seed if rng is not None and seed is not None else None
        self.spec = (style, text, scale, self.seed)
        self.style = style or rng.choice(("tag", "throwup", "throwup", "piece"))
        self.scale = scale
        self.angle = rng.uniform(-9, 5)
        self.pal = rng.choice(PALETTES)
        self.sign = rng.choice(SIGNS)
        extras = ["crown", "stars", "xxx", "arrow", "halo"]
        rng.shuffle(extras)
        self.extras = set(extras[: rng.randint(1, 3)])
        if self.style == "tag":
            self.text = text or rng.choice(TAGS)
            kind = rng.choice(("hand", "hand", "marker"))
            self.col = _c(rng.choice(TAG_COLOURS))
            self.path = text_path(self.text, kind, int(58 * scale))
            self.path = QTransform().shear(-0.25, 0).map(self.path)  # fast hand leans forward
            self.drips = _drips(rng, self.path, rng.randint(1, 3), 28 * scale)
        elif self.style == "throwup":
            self.text = text or rng.choice(THROWUPS)
            self.path = text_path(self.text, "bubble", int((96 if len(self.text) <= 5 else 74) * scale))
            self.drips = _drips(rng, self.path, rng.randint(2, 4), 40 * scale)
        else:
            self.text = text or rng.choice(PIECES)
            self.path = text_path(self.text, "hand", int((104 if len(self.text) <= 6 else 80) * scale))
            self.drips = _drips(rng, self.path, rng.randint(2, 5), 44 * scale)
            br = self.path.boundingRect()
            self.cloud = [(rng.uniform(br.left(), br.right()), rng.uniform(br.top() + 5, br.bottom() - 5),
                           rng.uniform(0.32, 0.55) * br.height()) for _ in range(int(br.width() / 40) + 5)]
        self.stars = [(rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(5, 12) * scale) for _ in range(4)]
        br = self.path.boundingRect()
        self.half_w, self.half_h = br.width() / 2, br.height() / 2

    def size(self):
        pad = 70 * self.scale + (40 * self.scale if self.style == "piece" else 0)
        w = 2 * self.half_w + 2 * pad
        h = 2 * self.half_h + 2 * pad + 50 * self.scale
        rad = math.radians(abs(self.angle))
        return int(w * math.cos(rad) + h * math.sin(rad)) + 10, int(h * math.cos(rad) + w * math.sin(rad)) + 10

    def main_colour(self) -> QColor:
        """The colour of the paint mist coming out of his can."""
        return QColor(self.col) if self.style == "tag" else _c(self.pal[0])

    def reveal_x(self, progress):
        """Local x of the spray edge at a given progress (matches the clip in paint)."""
        return -self.half_w - 60 + (2 * self.half_w + 160) * progress

    # ---- painting
    def paint(self, qp, cx, cy, progress=1.0, alpha=1.0):
        qp.save()
        qp.translate(cx, cy)
        qp.rotate(self.angle)
        if alpha < 1.0:
            qp.setOpacity(max(0.0, alpha))
        if progress < 1.0:  # sprayed on from left to right
            w, h = self.size()
            reveal = self.reveal_x(progress)
            qp.setClipRect(QRectF(-w, -h, reveal + w, 2 * h))
        getattr(self, "_paint_" + self.style)(qp)
        qp.restore()

    def _halo(self, qp, col, widths=((30, 28), (18, 55))):
        qp.setBrush(Qt.NoBrush)
        for w, a in widths:
            qp.setPen(QPen(_c(col, a), w * self.scale, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            qp.drawPath(self.path)

    def _drip_lines(self, qp, col, outline=None):
        for x, y, ln, r in self.drips:
            if outline is not None:
                qp.setPen(QPen(outline, (r + 1.6) * 2 * self.scale, Qt.SolidLine, Qt.RoundCap))
                qp.drawLine(QPointF(x, y), QPointF(x, y + ln))
            qp.setPen(QPen(col, r * 2 * self.scale, Qt.SolidLine, Qt.RoundCap))
            qp.drawLine(QPointF(x, y), QPointF(x, y + ln))

    def _paint_tag(self, qp):
        s, c = self.scale, self.col
        dark = c.lightness() < 60
        if "halo" in self.extras:
            self._halo(qp, (255, 255, 255) if dark else (c.red(), c.green(), c.blue()), ((16, 30),))
        self._drip_lines(qp, c)
        qp.setPen(QPen(QColor(255, 255, 255, 200) if dark else QColor(10, 10, 10, 200), 1.6 * s))
        qp.setBrush(c)
        qp.drawPath(self.path)
        # underline swoosh with an arrow head
        y = self.half_h + 14 * s
        sw = QPainterPath(QPointF(-self.half_w, y + 6 * s))
        sw.cubicTo(QPointF(-self.half_w * 0.3, y + 22 * s), QPointF(self.half_w * 0.4, y - 4 * s),
                   QPointF(self.half_w + 18 * s, y - 14 * s))
        qp.setBrush(Qt.NoBrush)
        qp.setPen(QPen(c, 5 * s, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        qp.drawPath(sw)
        tip = QPointF(self.half_w + 18 * s, y - 14 * s)
        qp.drawLine(tip, tip + QPointF(-14 * s, -2 * s))
        qp.drawLine(tip, tip + QPointF(-6 * s, 12 * s))
        if "crown" in self.extras:
            _crown(qp, -self.half_w + 10 * s, -self.half_h - 18 * s, 0.9 * s, c, outline=False)
        if "xxx" in self.extras:
            _xxx(qp, self.half_w - 30 * s, self.half_h + 40 * s, 0.7 * s)

    def _paint_throwup(self, qp):
        s = self.scale
        top, bottom, drop, spray = self.pal
        self._halo(qp, spray)  # every throw-up has overspray
        # 3D drop
        qp.setPen(Qt.NoPen)
        qp.setBrush(_c(drop))
        for i in range(9, 0, -1):
            qp.drawPath(self.path.translated(i * 1.3 * s, i * 1.3 * s))
        # outlines: white outer, black inner
        qp.setBrush(Qt.NoBrush)
        qp.setPen(QPen(QColor(255, 255, 255), 14 * s, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        qp.drawPath(self.path)
        qp.setPen(QPen(QColor(10, 10, 10), 8 * s, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        qp.drawPath(self.path)
        self._drip_lines(qp, _c(bottom), QColor(10, 10, 10))
        grad = QLinearGradient(0, -self.half_h, 0, self.half_h)
        grad.setColorAt(0, _c(top))
        grad.setColorAt(1, _c(bottom))
        qp.setPen(Qt.NoPen)
        qp.setBrush(grad)
        qp.drawPath(self.path)
        self._shine(qp)
        self._extras(qp)

    def _paint_piece(self, qp):
        s = self.scale
        top, bottom, drop, spray = self.pal
        # the cloud behind the letters
        cloud = QPainterPath()
        for x, y, r in self.cloud:
            cloud.addEllipse(QPointF(x, y), r * 1.25, r)
        cloud = cloud.simplified()
        self._halo_path(qp, cloud, spray)
        qp.setPen(QPen(QColor(10, 10, 10), 5 * s, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        qp.setBrush(_c(spray, 215))  # the cloud takes the overspray colour
        qp.drawPath(cloud)
        qp.setPen(Qt.NoPen)
        qp.setBrush(_c(drop))
        for i in range(10, 0, -1):
            qp.drawPath(self.path.translated(-i * 1.1 * s, i * 1.4 * s))
        qp.setBrush(Qt.NoBrush)
        qp.setPen(QPen(QColor(10, 10, 10), 9 * s, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        qp.drawPath(self.path)
        self._drip_lines(qp, _c(bottom), QColor(10, 10, 10))
        grad = QLinearGradient(0, -self.half_h, 0, self.half_h)
        grad.setColorAt(0, _c(top))
        grad.setColorAt(0.55, _c(bottom))
        grad.setColorAt(1, _c(top).darker(130))
        qp.setPen(Qt.NoPen)
        qp.setBrush(grad)
        qp.drawPath(self.path)
        self._shine(qp)
        self.extras.add("stars")
        self._extras(qp)
        sig = text_path(self.sign, "hand", int(26 * s))
        br = sig.boundingRect()
        qp.setPen(QPen(QColor(10, 10, 10), 1.2 * s))
        qp.setBrush(_c(spray))
        qp.drawPath(sig.translated(self.half_w - br.width() / 2, self.half_h + 34 * s))

    def _halo_path(self, qp, path, col):
        qp.setBrush(Qt.NoBrush)
        for w, a in ((34, 25), (18, 50)):
            qp.setPen(QPen(_c(col, a), w * self.scale, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            qp.drawPath(path)

    def _shine(self, qp):
        """White highlight along the top-left inside edge of every letter."""
        s = self.scale
        qp.save()
        qp.setClipPath(self.path, Qt.IntersectClip)
        qp.setBrush(Qt.NoBrush)
        qp.setPen(QPen(QColor(255, 255, 255, 230), 3.2 * s, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        qp.drawPath(self.path.translated(4 * s, 4 * s))
        qp.restore()

    def _extras(self, qp):
        s = self.scale
        if "stars" in self.extras:
            for fx, fy, r in self.stars:
                _star(qp, fx * (self.half_w + 20 * s), fy * (self.half_h + 18 * s), r, QColor(255, 255, 255, 235))
        if "crown" in self.extras:
            _crown(qp, -self.half_w + 18 * s, -self.half_h - 20 * s, s, QColor(255, 210, 40))
        if "xxx" in self.extras:
            _xxx(qp, 0, self.half_h + 36 * s, s)
        if "arrow" in self.extras:
            x0, y0 = self.half_w - 4 * s, -self.half_h * 0.2
            qp.setPen(QPen(QColor(10, 10, 10), 9 * s, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            arrow = QPolygonF([QPointF(x0, y0), QPointF(x0 + 40 * s, y0 - 26 * s)])
            qp.drawPolyline(arrow)
            col = _c(self.pal[0]) if self.style != "tag" else self.col
            qp.setPen(QPen(col, 5 * s, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            qp.drawPolyline(arrow)
            tip = QPointF(x0 + 40 * s, y0 - 26 * s)
            qp.setPen(Qt.NoPen)
            qp.setBrush(col)
            qp.drawPolygon(QPolygonF([tip + QPointF(8 * s, -6 * s), tip + QPointF(-14 * s, -6 * s),
                                      tip + QPointF(2 * s, 14 * s)]))


def render(piece: Piece) -> QImage:
    """The finished piece as an image (expensive: do it once, ideally in the helper process)."""
    w, h = piece.size()
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    qp = QPainter(img)
    qp.setRenderHint(QPainter.Antialiasing)
    piece.paint(qp, w / 2, h / 2)
    qp.end()
    return img


def paint_cached(qp, w, h, piece: Piece, img: QImage | None, progress=1.0, alpha=1.0, erase=0.0):
    """Reveal a pre-rendered piece up to the spray edge: an image blit, about a millisecond.
    erase 0..1: the graffiti crew has washed off everything left of that fraction of the width."""
    if img is None or progress <= 0 or erase >= 1.0:
        return
    if alpha < 1.0:
        qp.setOpacity(max(0.0, alpha))
    left = w * max(0.0, erase)
    right = w if progress >= 1.0 else max(0.0, w / 2 + piece.reveal_x(progress))
    if left > 0 or right < w:
        qp.setClipRect(QRectF(left, 0, max(0.0, right - left), h))
    qp.drawImage(0, 0, img)
