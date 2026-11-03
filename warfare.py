"""Complete warfare for the desktop dude: drones, a tank and airstrikes.

Everything stays temporary: shells and bombs go through the dude's explode()
(cursor shove, window shake that snaps back, fading scorch marks) and bullet holes fade.
Fight back: click drones to shoot them down, click the tank 3 times to blow it up,
drop landmines (Ctrl+Alt+M) and anti-air flak (Ctrl+Alt+F) at your cursor.
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

import tuning

OLIVE, DARK = QColor(78, 94, 52), QColor(32, 36, 26)
OUTLINE = QColor(255, 255, 255, 170)
BASE_FLAGS = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus


def _painter(widget):
    qp = QPainter(widget)
    qp.setRenderHint(QPainter.Antialiasing)
    return qp


class FxWindow(QWidget):
    """Always-on-top translucent window. Click-through unless clickable (and even then only its pixels)."""

    def __init__(self, w, h, clickable=False):
        super().__init__(None, BASE_FLAGS if clickable else BASE_FLAGS | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(w, h)
        self.w_, self.h_ = w, h

    def place_at(self, x, y):
        self.move(round(x - self.w_ / 2), round(y - self.h_ / 2))

    def kill(self):
        self.close()
        self.deleteLater()


class Tracer(FxWindow):
    """A bullet streak, visible for a few frames."""

    LIFE = 0.08

    def __init__(self, x1, y1, x2, y2):
        pad = 6
        left, top = round(min(x1, x2) - pad), round(min(y1, y2) - pad)
        super().__init__(int(abs(x2 - x1)) + 2 * pad + 2, int(abs(y2 - y1)) + 2 * pad + 2)
        self.move(left, top)
        self.p1, self.p2 = QPointF(x1 - left, y1 - top), QPointF(x2 - left, y2 - top)
        self.age = 0.0
        self.show()

    def step(self, dt) -> bool:
        self.age += dt
        if self.age >= self.LIFE:
            self.kill()
            return False
        return True

    def paintEvent(self, _):
        qp = _painter(self)
        qp.setPen(QPen(QColor(255, 230, 120, 230), 2, Qt.SolidLine, Qt.RoundCap))
        qp.drawLine(self.p1, self.p2)


class BulletHole(FxWindow):
    LIFE, FADE = 8.0, 2.5

    def __init__(self, x, y):
        super().__init__(24, 24)
        self.place_at(x, y)
        self.age = 0.0
        self.rays = [(random.uniform(0, math.tau), random.uniform(5, 10)) for _ in range(4)]
        self.show()

    def step(self, dt) -> bool:
        self.age += dt
        if self.age >= self.LIFE:
            self.kill()
            return False
        if self.age > self.LIFE - self.FADE:
            self.setWindowOpacity(max(0.0, (self.LIFE - self.age) / self.FADE))
        return True

    def paintEvent(self, _):
        qp = _painter(self)
        qp.setPen(QPen(QColor(20, 20, 20, 220), 1.2))
        for a, ln in self.rays:
            ca, sa = math.cos(a), math.sin(a)
            qp.drawLine(QPointF(12 + ca * 3, 12 + sa * 3), QPointF(12 + ca * ln, 12 + sa * ln))
        qp.setPen(QPen(OUTLINE, 1.2))
        qp.setBrush(QColor(15, 15, 15))
        qp.drawEllipse(QPointF(12, 12), 3.2, 3.2)


class Blast(FxWindow):
    """Small explosion: muzzle flashes, drone crashes, tank hits."""

    def __init__(self, x, y, radius=40, life=0.4):
        size = int(radius * 2.6) + 4
        super().__init__(size, size)
        self.place_at(x, y)
        self.r, self.life, self.age = radius, life, 0.0
        self.show()

    def step(self, dt) -> bool:
        self.age += dt
        if self.age >= self.life:
            self.kill()
            return False
        self.update()
        return True

    def paintEvent(self, _):
        qp = _painter(self)
        k = self.age / self.life
        fade = 1 - k
        c = QPointF(self.w_ / 2, self.h_ / 2)
        r = self.r * (0.35 + 0.65 * (1 - (1 - k) ** 2))
        qp.setPen(QPen(QColor(90, 90, 90, int(110 * fade)), 3))
        qp.setBrush(QColor(255, 120, 30, int(220 * fade)))
        qp.drawEllipse(c, r, r)
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(255, 225, 100, int(255 * fade**1.5)))
        qp.drawEllipse(c, r * 0.55, r * 0.55)


class Banner(FxWindow):
    """Blinking air-raid warning: your cue to move the cursor."""

    LIFE = 1.6

    def __init__(self, world):
        super().__init__(380, 56)
        self.place_at((world.left + world.right) / 2, world.top + 70)
        self.age = 0.0
        self.show()

    def step(self, dt) -> bool:
        self.age += dt
        if self.age >= self.LIFE:
            self.kill()
            return False
        self.update()
        return True

    def paintEvent(self, _):
        if int(self.age * 6) % 2:
            return
        qp = _painter(self)
        qp.setPen(QPen(QColor(255, 255, 255, 220), 2))
        qp.setBrush(QColor(200, 20, 20, 225))
        qp.drawRoundedRect(QRectF(2, 2, self.w_ - 4, self.h_ - 4), 10, 10)
        qp.setFont(QFont("Arial", 22, QFont.Black))
        qp.setPen(QColor(255, 255, 255))
        qp.drawText(QRectF(0, 0, self.w_, self.h_), Qt.AlignCenter, "LUCHTAANVAL!")


class Projectile(FxWindow):
    """Tank shell (straight and fast) or bomb (falls with gravity). Explodes via the dude's explode()."""

    def __init__(self, x, y, vx, vy, kind, reach=None, g=0.0):
        super().__init__(36, 36)
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.kind, self.reach, self.g, self.travel = kind, reach, g, 0.0
        self.place_at(x, y)
        self.show()

    def step(self, dt, cur, war) -> bool:
        world = war.d.world
        prev_y = self.y
        self.vy += self.g * dt
        sx, sy = self.vx * dt, self.vy * dt
        self.x, self.y = self.x + sx, self.y + sy
        self.travel += math.hypot(sx, sy)
        hit = None
        if self.kind == "bomb":  # bombs land on window tops too
            for p in world.plats:
                if p.x1 <= self.x <= p.x2 and prev_y < p.y <= self.y:
                    hit = (self.x, p.y)
                    break
        floor = world.floor_at(self.x)
        if hit is None and (
            self.y >= floor
            or not world.left <= self.x <= world.right
            or (self.reach is not None and self.travel >= self.reach)
            or math.hypot(cur[0] - self.x, cur[1] - self.y) < 26
        ):
            hit = world.clamp(self.x, min(self.y, floor - 4))
        if hit is not None:
            self.kill()
            war.d.explode(*hit)
            return False
        self.place_at(self.x, self.y)
        self.update()
        return True

    def paintEvent(self, _):
        qp = _painter(self)
        qp.translate(self.w_ / 2, self.h_ / 2)
        qp.rotate(math.degrees(math.atan2(self.vy, self.vx)))
        qp.setPen(QPen(OUTLINE, 1.2))
        if self.kind == "bomb":
            qp.setBrush(DARK)
            qp.drawEllipse(QRectF(-8, -4.5, 16, 9))
            qp.drawPolygon(QPolygonF([QPointF(-7, 0), QPointF(-13, -5), QPointF(-13, 5)]))
        else:
            qp.setBrush(QColor(190, 150, 60))
            qp.drawRoundedRect(QRectF(-7, -2.5, 12, 5), 2, 2)
            qp.setPen(Qt.NoPen)
            qp.setBrush(QColor(255, 200, 80, 160))
            qp.drawEllipse(QPointF(-10, 0), 5, 2)


class Drone(FxWindow):
    """Quadcopter that hovers near your cursor and fires short bursts. Click it to shoot it down."""

    LIFE = 22.0

    def __init__(self, x, y, slot):
        super().__init__(72, 48, clickable=True)
        self.x, self.y, self.vx, self.vy = x, y, 0.0, -250.0
        self.slot, self.t, self.spin = slot, 0.0, 0.0
        self.fire_cd = random.uniform(1.0, 2.0)
        self.shots, self.shot_cd = 0, 0.0
        self.hit = self.downed = False
        self.place_at(x, y)
        self.show()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.hit = True

    def step(self, dt, cur, btn, war) -> bool:
        self.t += dt
        world = war.d.world
        if self.hit and not self.downed:
            self.downed, self.vy = True, -120.0
            war.add_fx(Blast(self.x, self.y, 24, 0.35))
        if self.downed:  # spiral down and crash
            self.vy += 1500 * dt
            self.x += self.vx * dt
            self.y += self.vy * dt
            self.spin += 14 * dt
            if self.y >= world.floor_at(self.x) - 6:
                war.add_fx(Blast(self.x, self.y - 6, 34, 0.45))
                self.kill()
                return False
        else:
            leaving = self.t > self.LIFE
            if leaving:
                tx, ty = self.x, world.top - 150
            else:
                a = self.slot + self.t * 0.7
                tx = cur[0] + math.cos(a) * 170
                ty = max(world.top + 30, cur[1] - 110 + math.sin(a * 1.3) * 40)
            self.vx += ((tx - self.x) * 5.0 - self.vx * 3.2) * dt
            self.vy += ((ty - self.y) * 5.0 - self.vy * 3.2) * dt
            sp = math.hypot(self.vx, self.vy)
            if sp > 650:
                self.vx, self.vy = self.vx * 650 / sp, self.vy * 650 / sp
            self.x += self.vx * dt
            self.y += self.vy * dt
            if leaving and self.y < world.top - 40:
                self.kill()
                return False
            if not leaving and self.t > 1.5:
                self.shoot(dt, cur, btn, war)
        self.place_at(self.x, self.y)
        self.update()
        return True

    def shoot(self, dt, cur, btn, war):
        if self.shots > 0:  # mid-burst
            self.shot_cd -= dt
            if self.shot_cd <= 0:
                self.shots -= 1
                self.shot_cd = 0.09
                tx, ty = cur[0] + random.uniform(-16, 16), cur[1] + random.uniform(-16, 16)
                war.add_fx(Tracer(self.x, self.y + 7, tx, ty))
                war.d.terror.sfx.play("shot")
                war.bullet_hit(tx, ty, cur, btn)
            return
        self.fire_cd -= dt
        if self.fire_cd <= 0 and math.hypot(cur[0] - self.x, cur[1] - self.y) < 420:
            self.shots, self.shot_cd, self.fire_cd = 3, 0.0, random.uniform(1.6, 2.8)

    def paintEvent(self, _):
        qp = _painter(self)
        qp.translate(self.w_ / 2, self.h_ / 2)
        qp.rotate(math.degrees(self.spin) if self.downed else max(-20.0, min(20.0, self.vx * 0.04)))
        for w, col in ((5, OUTLINE), (3, DARK)):
            qp.setPen(QPen(col, w, Qt.SolidLine, Qt.RoundCap))
            qp.drawLine(QPointF(-20, -4), QPointF(20, -4))
        qp.setPen(Qt.NoPen)
        blur = 2.0 + 1.2 * abs(math.sin(self.t * 50))
        qp.setBrush(QColor(210, 210, 210, 130))
        for sx in (-20, 20):
            qp.drawEllipse(QPointF(sx, -7), 11, blur)
        qp.setPen(QPen(OUTLINE, 1.5))
        qp.setBrush(DARK)
        qp.drawRoundedRect(QRectF(-11, -6, 22, 11), 3, 3)
        qp.setBrush(QColor(15, 15, 15))
        qp.drawEllipse(QPointF(0, 7), 3, 3)
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(255, 40, 40) if int(self.t * 4) % 2 == 0 else QColor(90, 20, 20))
        qp.drawEllipse(QPointF(7, -1), 1.8, 1.8)


class Tank(FxWindow):
    """Parachutes in, drives along the floor and shells your cursor. Click it 3x to blow it up."""

    W, H, GY = 240, 240, 220  # GY = ground line inside the window
    LIFE = 26.0

    def __init__(self, x, world):
        super().__init__(self.W, self.H, clickable=True)
        self.x, self.y, self.vy = x, world.top + 40.0, 0.0
        self.dropping, self.f, self.aim = True, 1, -math.pi / 4
        self.hp, self.t, self.fire_cd = 3, 0.0, 1.8
        self.flash = self.recoil = self.track = 0.0
        self.hits_pending = 0
        self.target_flak = None
        self.place()
        self.show()

    def place(self):
        self.move(round(self.x - self.W / 2), round(self.y - self.GY))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and not self.dropping:
            self.hits_pending += 1

    def pivot(self):
        return self.x - self.f * 4, self.y - 44

    def step(self, dt, cur, btn, war) -> bool:
        world = war.d.world
        self.t += dt
        self.flash = max(0.0, self.flash - dt)
        self.recoil = max(0.0, self.recoil - dt * 4)
        ground = world.floor_at(self.x)
        if self.dropping:
            self.vy = min(self.vy + 900 * dt, 240.0)
            self.y += self.vy * dt
            if self.y >= ground:
                self.y, self.dropping = ground, False
                war.add_fx(Blast(self.x, ground - 4, 30, 0.35))
        else:
            self.y = ground
            dx = cur[0] - self.x
            self.f = 1 if dx >= 0 else -1
            want = 110.0 * self.f if abs(dx) > 420 else (-90.0 * self.f if abs(dx) < 200 else 0.0)
            self.x = min(max(self.x + want * dt, world.left + 90), world.right - 90)
            self.track += want * dt
            px, py = self.pivot()
            tx, ty = self.target_point(cur, war)
            ang = math.atan2(ty - py, tx - px)
            if ang > -0.08:  # never aim below the horizon
                ang = -0.08 if tx >= px else -math.pi + 0.08
            ang = max(ang, -math.pi + 0.08)
            self.aim += (ang - self.aim) * min(1.0, dt * 4)
            self.fire_cd -= dt
            if self.fire_cd <= 0:
                self.fire(cur, war)
        while self.hits_pending:
            self.hits_pending -= 1
            self.hp -= 1
            self.flash = 0.15
            war.add_fx(Blast(self.x + random.uniform(-30, 30), self.y - 30, 16, 0.25))
        if self.hp <= 0 or self.t > self.LIFE:
            self.kill()
            war.tank_done(self, destroyed=self.hp <= 0)
            return False
        self.place()
        self.update()
        return True

    def target_point(self, cur, war):
        f = self.target_flak
        if f is not None and f in war.flaks:
            return f.x, f.y - 22
        return cur

    def fire(self, cur, war):
        px, py = self.pivot()
        ux, uy = math.cos(self.aim), math.sin(self.aim)
        mx, my = px + ux * 50, py + uy * 50
        tx, ty = self.target_point(cur, war)
        reach = max(80.0, math.hypot(tx - mx, ty - my))
        self.target_flak = random.choice(war.flaks) if war.flaks and random.random() < 0.5 else None
        war.projectiles.append(Projectile(mx, my, ux * 1300, uy * 1300, "shell", reach=reach))
        war.add_fx(Blast(mx, my, 12, 0.15))
        self.recoil, self.fire_cd = 1.0, random.uniform(2.0, 3.2)
        war.d.terror.sfx.play("fire")

    def paintEvent(self, _):
        qp = _painter(self)
        cx, gy, f = self.W / 2, self.GY, self.f
        if self.dropping:  # parachute
            qp.setPen(QPen(QColor(235, 235, 235, 200), 1.2))
            for sx in (-60, -20, 20, 60):
                qp.drawLine(QPointF(cx + sx, gy - 170), QPointF(cx + sx * 0.45, gy - 40))
            qp.setPen(QPen(OUTLINE, 1.5))
            qp.setBrush(QColor(225, 225, 215))
            qp.drawChord(QRectF(cx - 70, gy - 215, 140, 90), 0, 180 * 16)
        if self.hp < 3:  # damage smoke
            qp.setPen(Qt.NoPen)
            for i in range((3 - self.hp) * 2):
                k = (self.t * 0.8 + i * 0.37) % 1.0
                qp.setBrush(QColor(90, 90, 90, int(150 * (1 - k))))
                qp.drawEllipse(QPointF(cx - 22 + i * 11, gy - 50 - k * 90), 6 + k * 10, 6 + k * 10)
        px, py = cx - f * 4, gy - 44  # barrel, behind the turret
        ux, uy = math.cos(self.aim), math.sin(self.aim)
        length = 50 - 10 * self.recoil
        for w, col in ((9, OUTLINE), (6, DARK)):
            qp.setPen(QPen(col, w, Qt.SolidLine, Qt.FlatCap))
            qp.drawLine(QPointF(px, py), QPointF(px + ux * length, py + uy * length))
        qp.setPen(QPen(OUTLINE, 2))  # tracks + wheels
        qp.setBrush(DARK)
        qp.drawRoundedRect(QRectF(cx - 62, gy - 20, 124, 20), 10, 10)
        a = self.track / 6
        for i in range(6):
            wx = cx - 50 + i * 20
            qp.setPen(QPen(OUTLINE, 1))
            qp.setBrush(QColor(80, 80, 80))
            qp.drawEllipse(QPointF(wx, gy - 10), 6, 6)
            qp.setPen(QPen(QColor(30, 30, 30), 1.5))
            qp.drawLine(QPointF(wx, gy - 10), QPointF(wx + math.cos(a) * 5, gy - 10 + math.sin(a) * 5))
        qp.setPen(QPen(OUTLINE, 2))  # hull + turret
        qp.setBrush(QColor(255, 255, 255) if self.flash > 0 else OLIVE)
        qp.drawPolygon(QPolygonF([
            QPointF(cx - 60, gy - 20), QPointF(cx + 60, gy - 20), QPointF(cx + 50, gy - 38), QPointF(cx - 54, gy - 38),
        ]))
        qp.drawChord(QRectF(cx - 30, gy - 62, 60, 40), 0, 180 * 16)
        hx, hy = cx + f * 14, gy - 70  # the dude in the hatch
        qp.setBrush(QColor(28, 28, 34))
        qp.drawEllipse(QPointF(hx, hy), 9, 9)
        qp.setBrush(OLIVE)
        qp.drawChord(QRectF(hx - 10, hy - 11, 20, 14), 0, 180 * 16)
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(255, 255, 255))
        qp.drawEllipse(QPointF(hx + 3.5 * f, hy - 1), 2, 2)


class Plane(FxWindow):
    """Flies over the top of the screen and carpet-bombs around where your cursor was."""

    def __init__(self, world, target_x):
        super().__init__(170, 130)
        self.f = random.choice((-1, 1))
        self.x = world.left - 90.0 if self.f > 0 else world.right + 90.0
        self.y = world.top + 70.0
        self.speed, self.t = 560.0, 0.0
        self.hp, self.crashing, self.vy, self.tilt, self.flash = 5, False, 0.0, 0.0, 0.0
        fall = math.sqrt(2 * max(world.floor_at(target_x) - self.y, 50) / 1500.0)
        drift = self.speed * 0.5 * fall  # bombs keep flying forward while they fall
        targets = [target_x + o for o in (-150, -50, 50, 150)]
        targets += [random.uniform(world.left + 100, world.right - 100) for _ in range(2)]
        drops = [t - self.f * drift for t in targets]
        self.drops = sorted((v for v in drops if world.left + 20 < v < world.right - 20), key=lambda v: v * self.f)
        self.place_at(self.x, self.y)
        self.show()

    def step(self, dt, war) -> bool:
        world = war.d.world
        self.t += dt
        self.flash = max(0.0, self.flash - dt)
        if self.hp <= 0:
            return self.crash(dt, war)
        self.x += self.f * self.speed * dt
        while self.drops and (self.x - self.drops[0]) * self.f >= 0:
            self.drops.pop(0)
            war.projectiles.append(Projectile(self.x, self.y + 16, self.f * self.speed * 0.5, 40.0, "bomb", g=1500.0))
        end = world.right + 100 if self.f > 0 else world.left - 100
        if (self.x - end) * self.f > 0:
            self.kill()
            return False
        self.place_at(self.x, self.y)
        self.update()
        return True

    def crash(self, dt, war) -> bool:
        """Shot down: nose-dives, no more bombs, explodes where it hits the ground."""
        world = war.d.world
        if not self.crashing:
            self.crashing, self.drops = True, []
            war.add_fx(Blast(self.x, self.y, 30, 0.4))
        self.vy += 650 * dt
        self.x += self.f * self.speed * 0.7 * dt
        self.y += self.vy * dt
        self.tilt = min(60.0, self.tilt + 60 * dt)
        floor = world.floor_at(self.x)
        if self.y >= floor - 10 or not world.left - 150 < self.x < world.right + 150:
            self.kill()
            if world.left <= self.x <= world.right:
                war.d.explode(self.x, min(self.y, floor - 10), hurt_cursor=False)
            return False
        self.place_at(self.x, self.y)
        self.update()
        return True

    def paintEvent(self, _):
        qp = _painter(self)
        qp.translate(self.w_ / 2, self.h_ / 2)
        qp.scale(self.f, 1)
        qp.rotate(self.tilt)
        qp.setPen(QPen(OUTLINE, 1.5))
        qp.setBrush(DARK)
        qp.drawPolygon(QPolygonF([QPointF(-46, -3), QPointF(-60, -24), QPointF(-48, -24), QPointF(-34, -5)]))
        qp.setBrush(QColor(255, 255, 255) if self.flash > 0 else OLIVE)
        qp.drawRoundedRect(QRectF(-56, -9, 106, 18), 9, 9)
        qp.setBrush(QColor(150, 200, 230))
        qp.drawChord(QRectF(14, -15, 24, 16), 0, 180 * 16)
        qp.setBrush(DARK)
        qp.drawRoundedRect(QRectF(-14, -2, 34, 8), 3, 3)
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(220, 220, 220, 140))
        qp.drawEllipse(QPointF(54, 0), 2.5, 16 * (0.4 + 0.6 * abs(math.sin(self.t * 40))))


class Puff(FxWindow):
    """Flak burst in the sky."""

    LIFE = 0.45

    def __init__(self, x, y):
        super().__init__(56, 56)
        self.place_at(x, y)
        self.age = 0.0
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
        c = QPointF(self.w_ / 2, self.h_ / 2)
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(60, 60, 60, int(200 * (1 - k))))
        qp.drawEllipse(c, 8 + 16 * k, 8 + 16 * k)
        if k < 0.25:
            qp.setBrush(QColor(255, 170, 60, int(230 * (1 - k / 0.25))))
            qp.drawEllipse(c, 6, 6)


class Mine(FxWindow):
    """Your landmine: wrecks tanks, launches the dude. Arms after a second."""

    ARM = 1.0

    def __init__(self, x, ground):
        super().__init__(40, 24)
        self.x, self.y, self.t, self.detonate = x, ground, 0.0, False
        self.move(round(x - 20), round(ground - 22))
        self.show()

    @property
    def armed(self):
        return self.t >= self.ARM

    def step(self, dt):
        self.t += dt
        self.update()

    def triggered(self, war) -> bool:
        if not self.armed:
            return False
        if self.detonate:
            return True
        tank, d = war.tank, war.d
        if tank is not None and not tank.dropping and abs(tank.x - self.x) < 60:
            tank.hits_pending += 2
            return True
        return (
            d.state not in ("tanking", "held", "climb")
            and d.on_ground
            and d.plat_hwnd is None
            and abs(d.x - self.x) < 16
        )

    def paintEvent(self, _):
        qp = _painter(self)
        qp.setPen(QPen(OUTLINE, 1.5))
        qp.setBrush(DARK)
        qp.drawRect(QRectF(5, 19, 30, 3))
        qp.setBrush(QColor(70, 82, 50))
        qp.drawChord(QRectF(7, 12, 26, 20), 0, 180 * 16)
        if not self.armed:
            light = QColor(240, 200, 40)
        else:
            light = QColor(255, 30, 30) if (self.t * 3) % 1 < 0.5 else QColor(90, 15, 15)
        qp.setPen(Qt.NoPen)
        qp.setBrush(light)
        qp.drawEllipse(QPointF(20, 14), 2.2, 2.2)


class Flak(FxWindow):
    """Your anti-air gun: auto-targets drones and the bomber. Explosions nearby wreck it."""

    LIFE, RANGE, RATE = 45.0, 1300.0, 0.25

    def __init__(self, x, ground):
        super().__init__(70, 70)
        self.x, self.y = x, ground
        self.aim, self.t, self.fire_cd, self.flash = -math.pi / 2, 0.0, 0.5, 0.0
        self.dead = False
        self.move(round(x - 35), round(ground - 66))
        self.show()

    def pivot(self):
        return self.x, self.y - 22

    def step(self, dt, war) -> bool:
        self.t += dt
        self.flash = max(0.0, self.flash - dt)
        if self.dead or self.t > self.LIFE:
            if self.dead:
                war.add_fx(Blast(self.x, self.y - 20, 26, 0.4))
            self.kill()
            return False
        px, py = self.pivot()
        targets = [t for t in war.air_targets() if math.hypot(t[1] - px, t[2] - py) < self.RANGE]
        if targets:
            obj, tx, ty = min(targets, key=lambda t: math.hypot(t[1] - px, t[2] - py))
            ang = math.atan2(ty - py, tx - px)
            if ang > -0.1:
                ang = -0.1 if tx >= px else -math.pi + 0.1
            ang = max(ang, -math.pi + 0.1)
            self.aim += (ang - self.aim) * min(1.0, dt * 10)
            self.fire_cd -= dt
            if self.fire_cd <= 0:
                self.fire_cd, self.flash = self.RATE, 0.06
                self.shoot(obj, tx, ty, war)
        self.update()
        return True

    def shoot(self, obj, tx, ty, war):
        px, py = self.pivot()
        ux, uy = math.cos(self.aim), math.sin(self.aim)
        war.add_fx(Tracer(px + ux * 26, py + uy * 26, px + ux * 150, py + uy * 150))
        war.d.terror.sfx.play("shot")
        is_plane = isinstance(obj, Plane)
        hit = random.random() < (0.5 if is_plane else 0.35)
        ox, oy = (0.0, 0.0) if hit else (random.uniform(-45, 45), random.uniform(-45, 45))
        war.add_fx(Puff(tx + ox, ty + oy))
        if hit and is_plane:
            obj.hp -= 1
            obj.flash = 0.1
        elif hit:
            obj.hit = True

    def paintEvent(self, _):
        qp = _painter(self)
        px, py = 35, 44
        ux, uy = math.cos(self.aim), math.sin(self.aim)
        nx, ny = -uy * 3, ux * 3
        for w, col in ((7, OUTLINE), (4, DARK)):  # twin barrels
            qp.setPen(QPen(col, w, Qt.SolidLine, Qt.FlatCap))
            for s in (-1, 1):
                qp.drawLine(QPointF(px + nx * s, py + ny * s), QPointF(px + nx * s + ux * 26, py + ny * s + uy * 26))
        if self.flash > 0:
            qp.setPen(Qt.NoPen)
            qp.setBrush(QColor(255, 220, 90, 230))
            qp.drawEllipse(QPointF(px + ux * 29, py + uy * 29), 6, 6)
        qp.setPen(QPen(OUTLINE, 1.5))
        qp.setBrush(QColor(60, 66, 50))
        qp.drawEllipse(QPointF(px, py), 9, 9)
        qp.setBrush(QColor(176, 150, 102))  # sandbags
        for bx in (6, 24, 42):
            qp.drawRoundedRect(QRectF(bx, 54, 22, 12), 5, 5)


class War:
    """Owns the heavy arsenal and escalates with the dude's rage."""

    def __init__(self, dude):
        self.d = dude
        self.enabled = True
        self.drones: list[Drone] = []
        self.projectiles: list[Projectile] = []
        self.fx: list = []
        self.tank: Tank | None = None
        self.plane: Plane | None = None
        self.banner: Banner | None = None
        self.mines: list[Mine] = []
        self.flaks: list[Flak] = []
        self.air_pending, self.air_target = 0.0, 0.0
        tn = self.tune = tuning.current()
        self.drone_cd, self.tank_cd, self.air_cd = tn.drones_first_s, tn.tank_first_s, tn.air_first_s

    def add_fx(self, w):
        self.fx.append(w)

    def place_mine(self, x):
        world = self.d.world
        x = min(max(x, world.left + 20), world.right - 20)
        if len(self.mines) >= 6:
            self.mines.pop(0).kill()
        self.mines.append(Mine(x, world.floor_at(x)))

    def place_flak(self, x):
        world = self.d.world
        x = min(max(x, world.left + 40), world.right - 40)
        if len(self.flaks) >= 2:
            self.flaks.pop(0).kill()
        self.flaks.append(Flak(x, world.floor_at(x)))

    def air_targets(self):
        out = [(dr, dr.x, dr.y) for dr in self.drones if not dr.hit and not dr.downed]
        if self.plane is not None and self.plane.hp > 0:
            out.append((self.plane, self.plane.x, self.plane.y))
        return out

    def on_explosion(self, x, y):
        """Any explosion wrecks nearby flak and sets off nearby mines (chain reactions)."""
        for f in self.flaks:
            if math.hypot(f.x - x, f.y - 30 - y) < 70:
                f.dead = True
        for m in self.mines:
            if m.armed and math.hypot(m.x - x, m.y - y) < 50:
                m.detonate = True

    def launch_drones(self, n):
        for i in range(n):
            self.drones.append(Drone(self.d.x, self.d.y - 70, i * math.tau / n))
        self.drone_cd = self.tune.drones_cooldown_s

    def deploy_tank(self):
        self.tank = Tank(self.d.x, self.d.world)
        self.tank_cd = self.tune.tank_cooldown_s

    def call_airstrike(self, target_x):
        self.air_pending, self.air_target = 1.6, target_x
        self.banner = Banner(self.d.world)
        self.air_cd = self.tune.air_cooldown_s

    def maybe_escalate(self, dt, cur, on_ground):
        """Roll for heavy weapons. Returns "air", "tank", "drones" or None. Numbers: tuning.py."""
        if not self.enabled:
            return None
        tn, r = self.tune, self.d.rage
        air_busy = self.plane is not None or self.air_pending > 0
        if r >= tn.rage_air and self.air_cd <= 0 and not air_busy and random.random() < tn.air_rate * dt:
            self.call_airstrike(cur[0])
            return "air"
        if (
            r >= tn.rage_tank
            and self.tank_cd <= 0
            and self.tank is None
            and on_ground
            and random.random() < tn.tank_rate * dt
        ):
            self.deploy_tank()
            return "tank"
        if r >= tn.rage_drones and self.drone_cd <= 0 and not self.drones and random.random() < tn.drones_rate * dt:
            self.launch_drones(3 if r >= tn.rage_drones_three else 2)
            return "drones"
        return None

    def bullet_hit(self, x, y, cur, btn):
        self.d.add_mark(BulletHole(x, y))
        if not btn and self.d.shove is None and math.hypot(cur[0] - x, cur[1] - y) < 20:
            a = random.uniform(0, math.tau)
            self.d.start_shove(cur, (cur[0] + math.cos(a) * 28, cur[1] + math.sin(a) * 28))

    def tank_done(self, tank, destroyed):
        """Tank expired or got blown up: the dude gets launched out of the hatch."""
        d = self.d
        d.x, d.y = tank.x, tank.y - 40
        d.on_ground, d.plat_hwnd, d.spin = False, None, 0.0
        d.vx, d.vy, d.spin_v = -tank.f * 220.0, -750.0, -tank.f * 9.0
        d.set_state("ragdoll")
        d.sync_visible()
        if destroyed:
            d.rage = min(1.0, d.rage + 0.1)
            d.explode(tank.x, tank.y - 30)
            d.terror.say("tank_down")

    def step(self, dt, cur, btn):
        self.drone_cd -= dt
        self.tank_cd -= dt
        self.air_cd -= dt
        if self.tank is not None:  # heavy armor doesn't stop the rest of the arsenal
            self.maybe_escalate(dt, cur, on_ground=False)
        if self.air_pending > 0:
            self.air_pending -= dt
            if self.air_pending <= 0:
                self.plane = Plane(self.d.world, self.air_target)
        if self.banner is not None and not self.banner.step(dt):
            self.banner = None
        self.drones = [x for x in self.drones if x.step(dt, cur, btn, self)]
        if self.tank is not None:
            if self.tank.step(dt, cur, btn, self):
                self.d.x, self.d.y = self.tank.x, self.tank.y - 5
            else:
                self.tank = None
        if self.plane is not None and not self.plane.step(dt, self):
            self.plane = None
        self.projectiles = [p for p in self.projectiles if p.step(dt, cur, self)]
        self.flaks = [f for f in self.flaks if f.step(dt, self)]
        booms, keep = [], []
        for m in self.mines:
            m.step(dt)
            if m.triggered(self):
                m.kill()
                booms.append((m.x, m.y - 8))
            else:
                keep.append(m)
        self.mines = keep
        for x, y in booms:
            self.d.explode(x, y, hurt_cursor=False)
        self.fx = [w for w in self.fx if w.step(dt)]

    def clear(self):
        """Ceasefire: remove everything right now."""
        for w in self.drones + self.projectiles + self.fx + self.mines + self.flaks:
            w.kill()
        for w in (self.plane, self.banner, self.tank):
            if w is not None:
                w.kill()
        if self.tank is not None:
            self.d.x, self.d.y = self.tank.x, self.tank.y - 10
        self.drones, self.projectiles, self.fx = [], [], []
        self.mines, self.flaks = [], []
        self.tank = self.plane = self.banner = None
        self.air_pending = 0.0
