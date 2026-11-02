"""The dude's life: he reacts to your apps, dances to your music, sleeps at night, holds grudges and
levels up, can be thrown in the Recycle Bin, duels you, hangs out on your taskbar, gets rained on
(real weather), calls in mini-dudes and, if you set it up, flickers your Home Assistant lights.

House rules still apply: nothing permanent. Lights always go back to how they were, the overlays
fade, and the only file he writes is his own save game (dude_save.json, gitignored).
"""

from __future__ import annotations

import dataclasses
import json
import math
import os
import random
import re
import threading
import time
import urllib.request
from pathlib import Path
from typing import ClassVar

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainterPath, QPen, QPolygonF

from arsenal import WEAPONS, PopText
from terror import LINES, _log
from warfare import OUTLINE, FxWindow, _painter

G = 2400.0
HERE = Path(__file__).resolve().parent

LINES.update({
    "watch": ["Ssst, film!", "Popcorn, mattie?", "Ewa, deze is goed", "Ga eens opzij, ik zie niks"],
    "work": ["Werk je wel, mattie?", "Laat je Claude het weer doen?", "Typ eens wat sneller, sukkel",
             "Kankersaai, dat werk van jou"],
    "dj": ["Draai eens een plaatje, DJ!", "Waar blijft de drop, tering?"],
    "dance": ["DIT IS MIJN PLAATJE!", "Wollah wat een beat", "Kom dan, dansen kanker!", "Oeee, harder!"],
    "sleep": ["Zzz... kanker... zzz", "Welterusten, sukkel"],
    "woken": ["Ik lag te slapen, kankerlijer!", "Tering, het is nacht!", "WIE MAAKT MIJ WAKKER?!"],
    "coffee": ["Eerst koffie, mattie", "Niet praten voor m'n koffie", "Bakkie pleur"],
    "clock": ["Hoe laat is het? Tijd om te slopen", "Mooi uitzicht hier, wollah", "Ik pas op je klok"],
    "start": ["Start? Ik start wel met slopen!", "Kankerknop", "Menuutje? Nee hoor"],
    "binned": ["WIE GOOIT MIJ IN DE PRULLENBAK?!", "Ik stink nu, KANKER!", "Dit vergeet ik nooit, wollah"],
    "grudge": ["Ik ben je niet vergeten, kanker", "Weet je nog wat je deed? Ik wel.", "Wraak, mattie. Wraak."],
    "levelup": ["LEVEL UP, kanker!", "Ik word sterker, sukkel", "Nieuw speelgoed, wollah!"],
    "challenge": ["Jij en ik. 1 tegen 1. NU.", "Duel, kanker! Kom dan!", "Best of 3, lafaard"],
    "duel_win": ["Ik ben de koning van je desktop!", "Te makkelijk, sukkel", "GG EZ, kanker"],
    "duel_lose": ["Geluk, kanker...", "Revanche! Ik wil revanche!", "Dit telt niet, wollah"],
    "coward": ["Lafaard! Kom terug!", "Rennen he, kankerkip"],
    "rain": ["Kankerweer weer", "Typisch Nederlands weer", "Wie heeft er aan de kraan gezeten?"],
    "snow": ["SNEEUW, kanker!", "Sneeuwpop bouwen, mattie!"],
    "storm": ["ONWEER! Tering!", "Ik ben niet bang, jij bent bang"],
    "minions": ["JONGENS! PAK HEM!", "Ik heb vrienden meegenomen", "Familie, aanvallen!"],
})

WATCH = re.compile(r"youtube|netflix|twitch|vlc|prime video|disney|videoland|npo start|soap2day|hbo|"
                   r"\bwatch\b|\bmovie|\bfilm|spiksplinter", re.IGNORECASE)
WORK = re.compile(r"visual studio|vs ?code|pycharm|powershell|terminal|command prompt|cmd\.exe|ubuntu|wsl|"
                  r"claude|obsidian|excel|word|outlook|teams|slack|jira|github", re.IGNORECASE)
DJ = re.compile(r"ableton|rekordbox|serato|traktor|fl studio|virtualdj|spotify|soundcloud|youtube music", re.IGNORECASE)

LEVELS = (0, 60, 180, 400, 800)
TIERS = (
    ("bat", "pan", "chicken", "pie", "haring"),
    ("golf", "boomerang", "pistol"),
    ("shotgun", "grenade", "mg"),
    ("chainsaw", "sniper", "dynamite"),
)
RAIN = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82}
SNOW = {71, 73, 75, 77, 85, 86}
STORM = {95, 96, 99}
STATES = ("watch", "dance", "sleep", "coffee", "sit", "kickstart", "binned", "build")
CHILL = ("idle", "wander")
BIN_NAMES = ("prullenbak", "recycle bin")


# --------------------------------------------------------------------------- poses (P = Pose class)


def pose_sit(P, t, eat=False):
    s = math.sin(t * 3) * 0.25
    if eat and math.sin(t * 2.5) > 0.55:
        arm_a = (2.0, 3.3)
    else:
        arm_a = (0.7, 1.5)
    return P(-0.12, (1.45, 1.35), (0.15 + s, -0.1 - s), (arm_a[0], 0.6), (arm_a[1], 1.6))


def pose_sleep(P, t):
    b = math.sin(t * 1.6) * 0.03
    return P(math.pi / 2 + b, (-math.pi / 2, -math.pi / 2 + 0.12), (-math.pi / 2, -math.pi / 2 + 0.25),
             (-1.45, -1.6), (-1.3, -1.7))


def pose_coffee(P, t):
    sip = math.sin(t * 2.1) > 0.7
    return P(0.02 - (0.08 if sip else 0), (0.12, -0.12), (0.06, -0.06), (1.7 if sip else 0.6, -0.2),
             (3.2 if sip else 2.2, -0.3))


def pose_dance(P, move, ph):
    s = math.sin(ph * math.pi)
    b = abs(s)
    if move == 0:  # headbang + fist pump
        return P(0.05 + 0.4 * b, (0.3, -0.3), (-0.1 - 0.4 * b, -0.1 - 0.4 * b), (2.6 + 0.3 * s, 0.4),
                 (2.9 + 0.3 * s, 0.9))
    if move == 1:  # hands in the air
        return P(0.06 * s, (0.35 * b, -0.35 * b), (-0.4 * b, -0.4 * b), (2.8 + 0.2 * s, -2.8 + 0.2 * s),
                 (3.1 + 0.4 * s, -3.1 + 0.4 * s))
    if move == 2:  # running man
        return P(0.1, (0.7 * s, -0.7 * s), (-0.6 * max(0, s), -0.6 * max(0, -s)), (0.3 - 0.8 * s, -0.3 + 0.8 * s),
                 (1.5 - 0.6 * s, -1.5 + 0.6 * s))
    sc = math.sin(ph * math.pi * 4)  # DJ: scratching + hand on the headphones
    return P(0.15 + 0.15 * b, (0.25, -0.25), (-0.25 * b, -0.25 * b), (1.2, 2.4), (1.6 + 0.45 * sc, 3.4))


# --------------------------------------------------------------------------- persistence


class Save:
    DEFAULTS: ClassVar[dict] = {"xp": 0, "grudge": 0.0, "punched": 0, "thrown": 0, "hits": 0, "duels_won": 0, "duels_lost": 0,
                "fish": 0, "binned": 0}

    def __init__(self, path: Path | None):
        self.path, self.data, self.dirty = path, dict(self.DEFAULTS), False
        if path is not None and path.exists():
            try:
                self.data.update({k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items()
                                  if k in self.DEFAULTS})
            except (OSError, ValueError) as e:
                _log(f"save unreadable, starting fresh: {e!r}")

    def __getitem__(self, k):
        return self.data[k]

    def __setitem__(self, k, v):
        self.data[k] = v
        self.dirty = True

    def write(self):
        if self.path is None or not self.dirty:
            return
        try:
            self.path.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
            self.dirty = False
        except OSError as e:
            _log(f"save failed: {e!r}")


# --------------------------------------------------------------------------- sensors


class Music:
    """Windows' output peak meter (what the volume mixer shows; nothing is recorded) + a crude beat detector."""

    def __init__(self, real):
        self.meter = None
        self.feed = None  # tests: callable returning a peak 0..1
        self.level = self.avg = 0.0
        self.loud_for = 0.0
        self.last_beat = -9.0
        self.beat = False
        self.t = 0.0
        if real:
            try:
                import ctypes

                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import AudioUtilities, IAudioMeterInformation

                dev = AudioUtilities.GetSpeakers()
                raw = getattr(dev, "_dev", dev)
                iface = raw.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None)
                self.meter = ctypes.cast(iface, ctypes.POINTER(IAudioMeterInformation))
            except Exception as e:  # noqa: BLE001 - no audio device / no pycaw: he just won't dance
                _log(f"music meter disabled: {e!r}")

    def peak(self):
        if self.feed is not None:
            return self.feed(self.t)
        if self.meter is None:
            return 0.0
        try:
            return float(self.meter.GetPeakValue())
        except Exception:  # noqa: BLE001
            return 0.0

    def step(self, dt):
        self.t += dt
        p = self.peak()
        self.level += (p - self.level) * min(1.0, dt * 2)
        self.avg += (p - self.avg) * min(1.0, dt * 4)
        self.loud_for = self.loud_for + dt if self.level > 0.03 else 0.0
        self.beat = p > max(0.06, self.avg * 1.35) and self.t - self.last_beat > 0.28
        if self.beat:
            self.last_beat = self.t

    @property
    def playing(self):
        return self.loud_for > 2.0


class Weather:
    """Current weather from Open-Meteo (free, no key), refreshed every 20 minutes.
    Location: dude_config.json next to this file ({"lat": 52.37, "lon": 4.9}), default Amsterdam."""

    URL = "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=weather_code,temperature_2m"

    def __init__(self, real):
        self.code, self.temp, self.next = None, None, 0.0
        self.real = real
        cfg = {}
        p = HERE / "dude_config.json"
        if real and p.exists():
            try:
                cfg = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                _log(f"dude_config.json unreadable: {e!r}")
        self.url = self.URL.format(lat=cfg.get("lat", 52.37), lon=cfg.get("lon", 4.90))

    def step(self, now):
        if self.real and now >= self.next:
            self.next = now + 20 * 60
            threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        try:
            with urllib.request.urlopen(self.url, timeout=10) as r:
                cur = json.loads(r.read())["current"]
            self.code, self.temp = int(cur["weather_code"]), cur["temperature_2m"]
        except Exception as e:  # noqa: BLE001
            _log(f"weather fetch failed: {e!r}")

    def kind(self):
        if self.code in STORM:
            return "storm"
        if self.code in SNOW:
            return "snow"
        if self.code in RAIN:
            return "rain"
        return None


class HomeAssistant:
    """Power cut for real: snapshot the lights that are on, switch them off, restore the snapshot ~2s later.
    Needs ha.json next to this file ({"url": "http://homeassistant.local:8123", "token": "<long-lived token>"})
    or HA_URL / HA_TOKEN. Not configured or offline = silently does nothing."""

    SCENE = "dude_power_cut"

    def __init__(self, real):
        self.url = self.token = None
        self.lights = None
        self.active = False
        self.status = "not set up"
        self.spawn = lambda fn: threading.Thread(target=fn, daemon=True).start()
        self.sleep = time.sleep
        if not real:
            return
        cfg = {}
        p = HERE / "ha.json"
        if p.exists():
            try:
                cfg = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                _log(f"ha.json unreadable: {e!r}")
        self.url = (cfg.get("url") or os.environ.get("HA_URL") or "").rstrip("/") or None
        self.token = cfg.get("token") or os.environ.get("HA_TOKEN")
        self.lights = cfg.get("lights")
        if self.url and self.token:
            self.status = "ready"

    @property
    def ready(self):
        return bool(self.url and self.token)

    def http(self, method, path, body=None):
        req = urllib.request.Request(self.url + path, method=method,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {self.token}",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=4) as r:
            return json.loads(r.read() or b"null")

    def flicker(self, dur=2.2):
        if not self.ready or self.active:
            return False
        self.active = True
        self.spawn(lambda: self._flicker(dur))
        return True

    def _flicker(self, dur):
        try:
            lights = self.lights
            if not lights:
                lights = [s["entity_id"] for s in self.http("GET", "/api/states")
                          if s["entity_id"].startswith("light.") and s["state"] == "on"]
            if not lights:
                self.status = "connected (no lights on)"
                return
            self.http("POST", "/api/services/scene/create", {"scene_id": self.SCENE, "snapshot_entities": lights})
            self.http("POST", "/api/services/light/turn_off", {"entity_id": lights})
            self.sleep(dur)
            self.restore()
            self.status = "connected"
        except Exception as e:  # noqa: BLE001
            self.status = "offline"
            _log(f"home assistant: {e!r}")
            self.restore()
        finally:
            self.active = False

    def restore(self):
        try:
            self.http("POST", "/api/services/scene/turn_on", {"entity_id": "scene." + self.SCENE})
        except Exception as e:  # noqa: BLE001
            _log(f"home assistant restore: {e!r}")


# --------------------------------------------------------------------------- overlays


class DuelHud(FxWindow):
    def __init__(self, duel):
        super().__init__(600, 150)
        self.duel = duel
        g = QGuiApplication.primaryScreen().geometry()
        self.move(g.x() + (g.width() - 600) // 2, g.y() + 30)
        self.show()

    def paintEvent(self, _):
        qp = _painter(self)
        du = self.duel
        f = QFont("Impact")
        f.setPixelSize(22)
        qp.setFont(f)
        for i, (name, col) in enumerate((("JIJ", QColor(60, 200, 90)), ("DUDE", QColor(220, 50, 50)))):
            x = 20 if i == 0 else 330
            qp.setPen(QPen(OUTLINE, 2))
            qp.setBrush(QColor(30, 30, 30, 200))
            qp.drawRoundedRect(QRectF(x, 30, 250, 26), 6, 6)
            w = 246 * max(0.0, du.hp[i]) / 100
            qp.setPen(Qt.NoPen)
            qp.setBrush(col)
            qp.drawRoundedRect(QRectF(x + 2 if i == 0 else x + 248 - w, 32, w, 22), 5, 5)
            qp.setPen(QColor(255, 255, 255))
            qp.drawText(QRectF(x, 2, 250, 26), Qt.AlignLeft if i == 0 else Qt.AlignRight, name)
        f.setPixelSize(30)
        qp.setFont(f)
        qp.setPen(QColor(255, 215, 40))
        qp.drawText(QRectF(250, 22, 100, 40), Qt.AlignCenter, f"{du.score[0]} - {du.score[1]}")
        if du.banner:
            f.setPixelSize(46)
            path = QPainterPath()
            path.addText(0, 0, f, du.banner)
            br = path.boundingRect()
            path.translate(300 - br.center().x(), 105 - br.center().y())
            qp.setPen(QPen(QColor(20, 20, 20), 6))
            qp.setBrush(Qt.NoBrush)
            qp.drawPath(path)
            qp.setPen(Qt.NoPen)
            qp.setBrush(QColor(255, 215, 40))
            qp.drawPath(path)


class Precip(FxWindow):
    """Rain / snow / thunderstorm over the primary screen. Click-through, ~30 seconds."""

    def __init__(self, kind, dur=30.0):
        g = QGuiApplication.primaryScreen().geometry()
        super().__init__(g.width(), g.height())
        self.move(g.x(), g.y())
        self.kind, self.dur, self.age, self.flash = kind, dur, 0.0, 0.0
        n = 90 if kind == "snow" else 160
        self.parts = [[random.uniform(0, g.width()), random.uniform(-g.height(), g.height()),
                       random.uniform(0.6, 1.4)] for _ in range(n)]
        self.frame = 0
        self.show()

    def step(self, dt) -> bool:
        self.age += dt
        if self.age >= self.dur:
            self.kill()
            return False
        h = self.h_
        for p in self.parts:
            if self.kind == "snow":
                p[1] += 60 * p[2] * dt
                p[0] += math.sin(self.age * 1.3 + p[2] * 7) * 25 * dt
            else:
                p[1] += 1100 * p[2] * dt
                p[0] -= 160 * dt
            if p[1] > h:
                p[1] -= h + 40
                p[0] = random.uniform(0, self.w_ + 200)
        self.flash = max(0.0, self.flash - dt)
        if self.kind == "storm" and random.random() < 0.1 * dt:
            self.flash = 0.15
        fade = min(1.0, self.age / 2, (self.dur - self.age) / 2)
        self.setWindowOpacity(max(0.0, fade))
        self.frame += 1
        if self.frame % 2 == 0:
            self.update()
        return True

    def paintEvent(self, _):
        qp = _painter(self)
        if self.flash > 0:
            qp.fillRect(self.rect(), QColor(255, 255, 255, int(110 * self.flash / 0.15)))
        if self.kind == "snow":
            qp.setPen(Qt.NoPen)
            qp.setBrush(QColor(255, 255, 255, 220))
            for x, y, s in self.parts:
                qp.drawEllipse(QPointF(x, y), 2.5 * s, 2.5 * s)
        else:
            qp.setPen(QPen(QColor(180, 210, 255, 150), 1.4))
            for x, y, s in self.parts:
                qp.drawLine(QPointF(x, y), QPointF(x - 3 * s, y + 16 * s))


class Snowman(FxWindow):
    LIFE = 60.0

    def __init__(self, x, floor):
        super().__init__(70, 90)
        self.move(round(x - 35), round(floor - 90))
        self.age = 0.0
        self.show()

    def step(self, dt) -> bool:
        self.age += dt
        if self.age >= self.LIFE:
            self.kill()
            return False
        if self.age > self.LIFE - 20:
            self.update()
        return True

    def paintEvent(self, _):
        qp = _painter(self)
        melt = max(0.0, (self.age - (self.LIFE - 20)) / 20)
        qp.translate(35, 90)
        qp.scale(1 + 0.3 * melt, 1 - 0.75 * melt)
        qp.setPen(QPen(QColor(150, 170, 200), 1.5))
        qp.setBrush(QColor(250, 252, 255))
        for cy, r in ((-16, 16), (-42, 12), (-62, 9)):
            qp.drawEllipse(QPointF(0, cy), r, r)
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(20, 20, 20))
        for dx in (-3.5, 3.5):
            qp.drawEllipse(QPointF(dx, -64), 1.4, 1.4)
        qp.setBrush(QColor(255, 130, 30))
        qp.drawPolygon(QPolygonF([QPointF(0, -61), QPointF(10, -59), QPointF(0, -58)]))
        qp.setPen(QPen(QColor(110, 70, 40), 2))
        qp.drawLine(QPointF(-11, -44), QPointF(-24, -54))
        qp.drawLine(QPointF(11, -44), QPointF(24, -52))


class Minion(FxWindow):
    """Mini-dude. Runs at your cursor and slaps it. Click it to make it go poof."""

    def __init__(self, life, x, y, f):
        super().__init__(80, 90, clickable=True)
        self.life, self.x, self.y = life, x, y
        self.vx, self.vy = random.uniform(-250, 250), -random.uniform(500, 800)
        self.f, self.on_ground, self.ph, self.cd = f, False, random.uniform(0, 6), 0.8
        self.age, self.dead, self.speed = 0.0, False, random.uniform(220, 300)
        self.place()
        self.show()

    def place(self):
        self.move(round(self.x - 40), round(self.y - 82))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.dead = True

    def step(self, dt, cur, btn) -> bool:
        lf = self.life
        world = lf.d.world
        self.age += dt
        self.cd -= dt
        if self.dead:
            lf.fx.append(PopText(self.x, self.y - 40, "POEF!"))
            self.kill()
            return False
        dx = cur[0] - self.x
        if self.age > 30:  # bored: run off screen
            self.vx = self.speed * (1 if self.x > (world.left + world.right) / 2 else -1)
            if not world.left - 40 < self.x < world.right + 40:
                self.kill()
                return False
        elif self.on_ground:
            self.vx = math.copysign(self.speed, dx) if abs(dx) > 12 else 0.0
            if cur[1] < self.y - 70 and abs(dx) < 170:
                self.vy, self.on_ground = -950.0, False
        if abs(self.vx) > 5:
            self.f = 1 if self.vx > 0 else -1
        prev = self.y
        self.vy += G * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        ground = world.floor_at(self.x)
        for p in world.plats:
            if p.x1 <= self.x <= p.x2 and prev <= p.y <= self.y and p.y < ground:
                ground = p.y
        self.on_ground = self.y >= ground and self.vy >= 0
        if self.on_ground:
            self.y, self.vy = ground, 0.0
        if self.age <= 30:
            self.x = min(max(self.x, world.left + 10), world.right - 10)
        self.ph += abs(self.vx) * dt / 14
        if math.hypot(dx, cur[1] - (self.y - 22)) < 36 and self.cd <= 0 and not btn:
            self.cd = 1.1
            lf.d.arsenal.fling_cursor(cur, math.copysign(120, dx), -60, 25, 0.22)
            lf.fx.append(PopText(cur[0], cur[1] - 30, "PATS!"))
        self.place()
        self.update()
        return True

    def paintEvent(self, _):
        qp = _painter(self)
        k = self.life.kit
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(0, 0, 0, 1))  # invisible, but makes the whole body clickable
        qp.drawEllipse(QPointF(40, 58), 22, 30)
        pose = k["pose_walk"](self.ph, 0.6, 0.15, 0.6) if abs(self.vx) > 5 else k["pose_stand"](self.age)
        k["draw"](qp, 40, 82, pose, self.f, QColor(170, 40, 40), 0.5)


# --------------------------------------------------------------------------- the duel


class Duel:
    DMG_DUDE: ClassVar[dict] = {"punched": 22, "thrown": 30, "boom": 15}

    def __init__(self, life):
        self.life = life
        d = life.d
        self.hp, self.score, self.round = [100.0, 100.0], [0, 0], 1
        self.phase, self.t, self.banner, self.away = "intro", 0.0, "RONDE 1", 0.0
        self.prev = (d.terror.enabled, d.war.enabled)
        d.terror.enabled = d.war.enabled = False
        self.hud = DuelHud(self)
        d.terror.say("challenge")

    def hit_player(self, dmg):
        if self.phase == "fight":
            self.hp[0] -= dmg
            self.hud.update()

    def hit_dude(self, kind):
        if self.phase == "fight":
            self.hp[1] -= self.DMG_DUDE.get(kind, 15)
            self.hud.update()

    def step(self, dt, cur):
        d = self.life.d
        self.t += dt
        d.rage = 1.0
        if self.phase == "intro" and self.t > 1.8:
            self.phase, self.t, self.banner = "fight", 0.0, "FIGHT!"
        elif self.phase == "fight":
            if self.t > 1.0:
                self.banner = ""
            far = math.hypot(cur[0] - d.x, cur[1] - d.y) > 1100
            self.away = self.away + dt if far else 0.0
            if self.away > 20:
                d.terror.say("coward")
                self.hp[0] = 0
            if self.hp[0] <= 0 or self.hp[1] <= 0:
                won = 1 if self.hp[0] <= 0 else 0
                self.score[won] += 1
                self.phase, self.t = "between", 0.0
                self.banner = "KO! " + ("DUDE WINT" if won else "JIJ WINT")
        elif self.phase == "between" and self.t > 2.6:
            if max(self.score) >= 2:
                self.life.end_duel(winner=0 if self.score[0] > self.score[1] else 1)
                return
            self.round += 1
            self.hp = [100.0, 100.0]
            self.phase, self.t, self.banner = "intro", 0.0, f"RONDE {self.round}"
        self.hud.update()

    def close(self):
        d = self.life.d
        d.terror.enabled, d.war.enabled = self.prev
        self.hud.kill()


# --------------------------------------------------------------------------- life itself


class Life:
    def __init__(self, dude, kit, real):
        self.d, self.kit, self.real = dude, kit, real
        self.P = kit["Pose"]
        self.save = Save(HERE / "dude_save.json" if real else None)
        self.music = Music(real)
        self.weather = Weather(real)
        self.ha = HomeAssistant(real)
        self.hour_fn = (lambda: time.localtime().tm_hour) if real else (lambda: 14)
        self.title = ""
        self.parts: dict = {}
        self.fx: list = []
        self.minions: list[Minion] = []
        self.marks: list = []
        self.precip: Precip | None = None
        self.duel: Duel | None = None
        self.goal: dict = {}
        self.cd = {"watch": 20.0, "work": 30.0, "dj": 40.0, "coffee": 60.0, "taskbar": 45.0, "dance": 5.0,
                   "sleep": 10.0, "challenge": 300.0, "minions": 60.0, "shower": 30.0, "bin": 0.0}
        self.next_scan, self.next_save, self.next_tray, self.last_hit = 0.0, 30.0, 0.0, -9.0
        self.soot = 0.0
        self.t = 0.0
        g = self.save["grudge"]
        if g >= 1:
            dude.rage = max(dude.rage, min(0.6, g * 0.06))
            dude.terror.later(3.0, lambda: dude.terror.say("grudge"))

    # ---- facts
    @property
    def level(self):
        return sum(1 for x in LEVELS if self.save["xp"] >= x)

    def unlocked(self):
        out = set()
        for tier in TIERS[: self.level]:
            out.update(tier)
        if self.level >= len(TIERS):
            out.update(WEAPONS)
        return out

    def night(self):
        h = self.hour_fn()
        return h >= 23 or h < 6

    def hidden(self):
        return self.d.state == "binned"

    @property
    def FROZEN(self):
        if self.d.state == "binned" or (self.d.state == "sit" and self.goal.get("phase") == "sit"):
            return (self.d.state,)
        return ()

    def app(self):
        t = self.title
        if WATCH.search(t):
            return "watch"
        if DJ.search(t):
            return "dj"
        if WORK.search(t):
            return "work"
        return None

    # ---- events from the dude
    def gain(self, xp):
        before = self.level
        self.save["xp"] += xp
        if self.level > before:
            d = self.d
            self.fx.append(PopText(d.x, d.y - 150, f"LEVEL {self.level}!"))
            d.terror.say("levelup")
            d.terror.sfx.play("ding")

    def cursor_hit(self, dmg=10):
        """He (or his weapons, minions, explosions) just hit your cursor."""
        if self.t - self.last_hit < 0.35:
            return
        self.last_hit = self.t
        self.save["hits"] += 1
        self.gain(4)
        if self.duel is not None:
            self.duel.hit_player(dmg)

    def dude_hit(self, kind):
        """You hit him."""
        if kind in ("punched", "thrown"):
            self.save[kind] += 1
        self.save["grudge"] = min(20.0, self.save["grudge"] + {"punched": 0.3, "thrown": 0.5}.get(kind, 0.15))
        if self.duel is not None:
            self.duel.hit_dude(kind)

    def fish_eaten(self):
        self.save["fish"] += 1
        self.gain(15)

    # ---- triggers (tray, hotkey, tests)
    def trigger(self, kind) -> bool:
        d = self.d
        if kind == "duel":
            return self.toggle_duel()
        if kind == "minions":
            return self.spawn_minions()
        if kind in ("rain", "snow", "storm"):
            return self.start_shower(kind)
        if kind == "power":
            return self.ha.flicker()
        if d.state in ("held", "ragdoll", "tanking", "binned"):
            return False
        if kind == "clock":
            return self.go_taskbar("clock")
        if kind == "start":
            return self.go_taskbar("start")
        if kind in ("watch", "sleep", "coffee", "dance"):
            self.begin(kind)
            return True
        return False

    def toggle_duel(self):
        if self.duel is not None:
            self.end_duel(None)
            return True
        if getattr(self.d, "paused", False):
            return False
        self.duel = Duel(self)
        if self.d.state in STATES:
            self.d.set_state("idle", 0.5)
        return True

    def end_duel(self, winner):
        du, self.duel = self.duel, None
        if du is None:
            return
        du.close()
        if winner == 1:
            self.save["duels_won"] += 1
            self.gain(40)
            self.d.terror.say("duel_win")
        elif winner == 0:
            self.save["duels_lost"] += 1
            self.gain(10)
            self.d.terror.say("duel_lose")
        self.save.write()

    def spawn_minions(self, n=3):
        d = self.d
        n = min(n, 3 - len(self.minions))
        if n <= 0:
            return False
        for _ in range(n):
            self.minions.append(Minion(self, d.x + random.uniform(-20, 20), d.y - 40, d.f))
        d.terror.say("minions")
        return True

    def start_shower(self, kind, dur=30.0):
        if self.precip is not None:
            self.precip.kill()
        self.precip = Precip(kind, dur)
        self.d.terror.say(kind)
        if kind == "storm":
            self.d.terror.sfx.play("rumble")
        d = self.d
        if kind == "snow" and d.state in CHILL and d.on_ground:
            d.vx = 0.0
            d.set_state("build", 3.0)
        return True

    def go_taskbar(self, what):
        d = self.d
        r = self.parts.get(what)
        if r is None:
            return False
        floor = d.world.floor_at((r[0] + r[2]) / 2)
        if abs(r[1] - floor) > 8:  # taskbar isn't at the bottom: skip
            return False
        if what == "clock":
            tx, face = (r[0] + r[2]) / 2, random.choice((-1, 1))
        else:
            right = r[2] + 24
            tx, face = (right, -1) if right < d.world.right - 30 else (r[0] - 24, 1)
        self.goal = {"what": what, "phase": "go", "x": tx, "face": face, "top": r[1], "rect": r}
        d.set_state("sit" if what == "clock" else "kickstart", 99.0)
        return True

    def begin(self, kind):
        d = self.d
        d.vx = 0.0
        self.goal = {"phase": kind, "beats": 0, "move": random.randrange(4), "ph": 0.0, "near": 0.0}
        d.set_state(kind, {"watch": random.uniform(12, 25), "sleep": random.uniform(40, 120),
                           "coffee": 8.0, "dance": random.uniform(10, 20)}[kind])
        d.terror.say(kind)

    # ---- per-frame
    def think(self, dt, cur, btn) -> bool:
        d = self.d
        s = d.state
        if self.duel is not None:
            if s in STATES:
                d.set_state("idle", 0.3)
            if d.state in CHILL:
                d.set_state("chase", 7.0)
            return False
        if s in STATES:
            getattr(self, "run_" + s)(dt, cur, btn)
            return True
        return s in CHILL and self.maybe_start(dt, cur, btn)

    def maybe_start(self, dt, cur, btn):
        d = self.d
        if btn or d.rage > 0.5 or not d.on_ground:
            return False
        dist = math.hypot(cur[0] - d.x, cur[1] - (d.y - 50))
        cd = self.cd
        if self.night() and cd["sleep"] <= 0 and dist > 250 and not self.music.playing and random.random() < 0.15 * dt:
            cd["sleep"] = 60.0
            self.begin("sleep")
            return True
        if self.music.playing and cd["dance"] <= 0 and random.random() < 0.3 * dt:
            cd["dance"] = random.uniform(15, 40)
            self.begin("dance")
            return True
        app = self.app()
        if app == "watch" and cd["watch"] <= 0 and random.random() < 0.12 * dt:
            cd["watch"] = random.uniform(40, 90)
            self.begin("watch")
            return True
        if app in ("work", "dj") and cd[app] <= 0 and random.random() < 0.05 * dt:
            cd[app] = random.uniform(90, 180)
            d.terror.say(app)
            d.set_state("taunt", 1.2)
            return True
        h = self.hour_fn()
        if 6 <= h < 10 and cd["coffee"] <= 0 and random.random() < 0.04 * dt:
            cd["coffee"] = 600.0
            self.begin("coffee")
            return True
        if self.parts and cd["taskbar"] <= 0 and random.random() < 0.03 * dt:
            cd["taskbar"] = random.uniform(90, 200)
            return self.go_taskbar(random.choice(("clock", "clock", "start")))
        return False

    def stand_up(self, rage_to=None):
        d = self.d
        if rage_to is not None:
            d.rage = max(d.rage, rage_to)
            d.set_state("notice", 0.45)
        else:
            d.set_state("idle", 1.0)
        self.goal = {}

    def run_watch(self, dt, cur, btn):
        d = self.d
        d.vx = 0.0
        if math.hypot(cur[0] - d.x, cur[1] - (d.y - 30)) < 140:
            self.goal["near"] += dt
            if self.goal["near"] > 1.0 and random.random() < 0.02:
                d.terror.say("watch")
            if d.rage > 0.4 and self.goal["near"] > 1.5:
                self.stand_up(d.rage)
                return
        if d.st > d.state_len:
            self.stand_up()

    def run_dance(self, dt, cur, btn):
        d, g = self.d, self.goal
        d.vx = 0.0
        if self.music.beat:
            g["beats"] += 1
            g["ph"] = 0.0
            if g["beats"] % 8 == 0:
                g["move"] = (g["move"] + random.randint(1, 3)) % 4
                d.f = -d.f
        g["ph"] = min(1.0, g["ph"] + dt * 3)
        if (not self.music.playing and self.music.loud_for == 0 and d.st > 2) or d.st > d.state_len:
            self.stand_up()
        elif d.rage > 0.5 and math.hypot(cur[0] - d.x, cur[1] - (d.y - 50)) < 70:
            self.stand_up(d.rage)

    def run_sleep(self, dt, cur, btn):
        d, g = self.d, self.goal
        d.vx = 0.0
        near = math.hypot(cur[0] - d.x, cur[1] - (d.y - 10)) < 110
        g["near"] = g["near"] + dt if near else 0.0
        if g["near"] > 0.6:
            self.save["grudge"] += 0.3
            d.terror.say("woken")
            self.stand_up(0.7)
        elif d.st > d.state_len:
            self.stand_up()

    def run_coffee(self, dt, cur, btn):
        self.d.vx = 0.0
        if self.d.st > self.d.state_len:
            self.stand_up()

    def run_build(self, dt, cur, btn):
        d = self.d
        d.vx = 0.0
        if d.st > d.state_len:
            self.marks.append(Snowman(d.x + 45 * d.f, d.world.floor_at(d.x + 45 * d.f)))
            d.set_state("taunt", 1.2)

    def _walk_to(self, dt, tx):
        d = self.d
        dx = tx - d.x
        if abs(dx) > 10:
            d.walk(math.copysign(260, dx))
        else:
            d.vx = 0.0
        floor = d.world.floor_at(tx)
        d.navigate(tx, floor, dt)
        return abs(dx) <= 10 and d.on_ground and abs(d.y - floor) < 4

    def run_sit(self, dt, cur, btn):
        d, g = self.d, self.goal
        if not g:
            self.stand_up()
            return
        if g["phase"] == "go":
            if self._walk_to(dt, g["x"]):
                g["phase"], g["until"] = "sit", d.st + random.uniform(15, 30)
                d.vx, d.vy, d.x, d.y, d.f = 0.0, 0.0, g["x"], g["top"] + 20, g["face"]
                d.on_ground = False
                d.terror.say("clock")
            elif d.st > 15:
                self.stand_up()
            return
        d.vx = 0.0
        if math.hypot(cur[0] - d.x, cur[1] - (d.y - 40)) < 100 or d.st > g["until"]:
            d.y, d.vy = g["top"], -600.0
            near = math.hypot(cur[0] - d.x, cur[1] - (d.y - 40)) < 100
            self.stand_up(0.5 if near else None)

    def run_kickstart(self, dt, cur, btn):
        d, g = self.d, self.goal
        if not g:
            self.stand_up()
            return
        if g["phase"] == "go":
            if self._walk_to(dt, g["x"]):
                g["phase"], g["t0"] = "kick", d.st
                d.vx, d.f = 0.0, g["face"]
            elif d.st > 15:
                self.stand_up()
            return
        d.vx = 0.0
        k = (d.st - g["t0"]) / 0.45
        g["k"] = min(1.0, k)
        if k >= 0.4 and not g.get("hit"):
            g["hit"] = True
            r = g["rect"]
            self.fx.append(PopText((r[0] + r[2]) / 2, r[1] - 30, "BONK!"))
            d.terror.sfx.play("bonk")
            d.terror.say("start")
        if k >= 1.6:
            self.goal = {}
            d.set_state("taunt", 1.2)

    def run_binned(self, dt, cur, btn):
        d, g = self.d, self.goal
        d.vx = d.vy = 0.0
        if d.st > g.get("rattle", 0):
            g["rattle"] = d.st + 1.1
            r = g["rect"]
            self.fx.append(PopText((r[0] + r[2]) / 2 + random.uniform(-15, 15), r[1] - 10,
                                   random.choice(("BONK", "KLANG", "!!", "TERING"))))
        if d.st > d.state_len:
            r = g["rect"]
            d.x, d.y = (r[0] + r[2]) / 2, r[1]
            d.vx, d.vy, d.spin_v = random.choice((-350, 350)), -1100.0, 8.0
            d.on_ground, d.plat_hwnd = False, None
            d.rage = 1.0
            self.soot = 25.0
            self.cd["bin"] = 8.0
            self.goal = {}
            d.set_state("ragdoll", 1.0)
            d.terror.say("binned")

    def bin_rect(self):
        for name, r in self.d.terror.probe.icons:
            if name.strip().lower() in BIN_NAMES:
                return r
        return None

    def step(self, dt, cur, btn):
        d = self.d
        self.t += dt
        for k in self.cd:
            self.cd[k] -= dt
        self.soot = max(0.0, self.soot - dt)
        self.music.step(dt)
        self.weather.step(self.t)
        g = self.save["grudge"]
        self.save.data["grudge"] = max(0.0, g - dt * 0.02 / 60)
        if g >= 1 and self.duel is None:
            d.rage = max(d.rage, min(0.45, g * 0.04))
        if self.t >= self.next_scan:
            self.next_scan = self.t + 2.0
            self.title = d.w32.foreground_title()
            if int(self.t) % 20 < 2:
                self.parts = d.w32.taskbar_parts()
                d.terror.probe.request("icons")
        # thrown in the bin?
        if d.state == "ragdoll" and self.duel is None and self.cd["bin"] <= 0:
            r = self.bin_rect()
            hx, hy = d.limb("hip")
            if r and r[0] - 8 <= hx <= r[2] + 8 and r[1] - 8 <= hy <= r[3] + 8:
                self.goal = {"rect": r}
                self.save["binned"] += 1
                d.set_state("binned", 6.0)
        # weather
        kind = self.weather.kind()
        if kind and self.cd["shower"] <= 0 and self.precip is None and d.state != "binned":
            self.cd["shower"] = random.uniform(240, 480)
            self.start_shower(kind)
        if self.precip is not None and not self.precip.step(dt):
            self.precip = None
        # duel / minions
        if self.duel is not None:
            self.duel.step(dt, cur)
        elif (d.state == "chase" and self.save["grudge"] >= 4 and self.cd["challenge"] <= 0
              and random.random() < 0.02 * dt):
            self.cd["challenge"] = 600.0
            self.toggle_duel()
        if d.state == "chase" and d.rage >= 0.9 and self.cd["minions"] <= 0 and random.random() < 0.08 * dt:
            self.cd["minions"] = random.uniform(90, 150)
            self.spawn_minions()
        self.minions = [m for m in self.minions if m.step(dt, cur, btn)]
        self.fx = [w for w in self.fx if w.step(dt)]
        self.marks = [w for w in self.marks if w.step(dt)]
        if self.t >= self.next_save:
            self.next_save = self.t + 30.0
            self.save.write()
        if self.t >= self.next_tray:
            self.next_tray = self.t + 2.0
            self.update_tray()

    def update_tray(self):
        tray = getattr(self.d, "tray", None)
        a = getattr(tray, "life_action", None) if tray else None
        if a is not None:
            s = self.save
            a.setText(f"Level {self.level} · {s['xp']} XP · grudge {s['grudge']:.1f} · "
                      f"duels {s['duels_won']}-{s['duels_lost']}")
        b = getattr(tray, "ha_action", None) if tray else None
        if b is not None:
            b.setText(f"Home Assistant: {self.ha.status}")

    # ---- looks
    def pose(self):
        d, P = self.d, self.P
        s = d.state
        if s == "watch":
            return pose_sit(P, d.t, eat=True)
        if s == "sit":
            if self.goal.get("phase") == "sit":
                return pose_sit(P, d.t)
            return None
        if s == "sleep":
            return pose_sleep(P, d.t)
        if s == "coffee":
            return pose_coffee(P, d.t)
        if s == "dance":
            g = self.goal
            return pose_dance(P, g.get("move", 0), g.get("ph", 0.0))
        if s == "build":
            return self.kit["pose_crouch"]()
        if s == "kickstart" and self.goal.get("phase") == "kick":
            return self.kit["pose_kick"](min(1.0, self.goal.get("k", 0.0)))
        return None

    def adjust_pose(self, pose):
        """Umbrella up when it rains."""
        if (self.precip is not None and self.precip.kind in ("rain", "storm")
                and self.d.state in ("idle", "wander", "chase", "notice", "coffee")):
            return dataclasses.replace(pose, upper=(pose.upper[0], -2.8), lower=(pose.lower[0], -3.05))
        return pose

    def tint(self, color):
        if self.soot > 0:
            k = min(1.0, self.soot / 5)
            return QColor(int(color.red() + (95 - color.red()) * k), int(color.green() + (80 - color.green()) * k),
                          int(color.blue() + (60 - color.blue()) * k))
        return color

    def paint(self, qp, ox, oy, pose, f):
        d = self.d
        pts = self.kit["skeleton"](pose, f)

        def at(name):
            return ox + pts[name][0], oy + pts[name][1]

        s = d.state
        t = d.t
        hx, hy = at("head")
        if self.night() and s not in ("binned",):
            ang = (pose.lean + pose.spin) * f
            qp.save()
            qp.translate(hx, hy)
            qp.rotate(math.degrees(ang))
            qp.setPen(QPen(OUTLINE, 1.2))
            qp.setBrush(QColor(60, 90, 200))
            qp.drawPolygon(QPolygonF([QPointF(-10, -5), QPointF(10, -5), QPointF(-f * 18, -24)]))
            qp.setBrush(QColor(250, 250, 250))
            qp.drawEllipse(QPointF(-f * 18, -24), 3.5, 3.5)
            qp.restore()
        if s == "sleep":
            f_ = QFont("Impact")
            for i in range(3):
                k = (t * 0.6 + i / 3) % 1.0
                f_.setPixelSize(int(11 + 6 * k))
                qp.setFont(f_)
                qp.setPen(QColor(255, 255, 255, int(230 * (1 - k))))
                qp.drawText(QPointF(hx + f * (8 + 18 * k), hy - 12 - 40 * k), "Z")
        if s == "watch":
            bx, by = at("hand_b")
            qp.setPen(QPen(OUTLINE, 1.2))
            for i in range(4):
                qp.setBrush(QColor(220, 30, 30) if i % 2 == 0 else QColor(250, 250, 250))
                qp.drawPolygon(QPolygonF([QPointF(bx - 8 + i * 4, by - 14), QPointF(bx - 4 + i * 4, by - 14),
                                          QPointF(bx - 3 + i * 3, by + 2), QPointF(bx - 6 + i * 3, by + 2)]))
            qp.setPen(Qt.NoPen)
            qp.setBrush(QColor(255, 240, 180))
            for dx_ in (-6, -2, 2, 6, -4, 4):
                qp.drawEllipse(QPointF(bx + dx_, by - 16 - (2 if abs(dx_) < 5 else 0)), 2.6, 2.6)
        if s == "coffee":
            ax, ay = at("hand_a")
            qp.setPen(QPen(OUTLINE, 1.2))
            qp.setBrush(QColor(245, 245, 245))
            qp.drawRoundedRect(QRectF(ax - 4, ay - 10, 10, 12), 2, 2)
            qp.setBrush(Qt.NoBrush)
            qp.drawEllipse(QPointF(ax + 8, ay - 4), 3, 3)
            qp.setPen(QPen(QColor(255, 255, 255, 160), 1.5))
            for i in range(2):
                y0 = ay - 13 - ((t * 15 + i * 8) % 16)
                qp.drawLine(QPointF(ax + i * 4, y0), QPointF(ax + i * 4 + 2 * math.sin(t * 5 + i), y0 - 5))
        if s == "dance" and self.goal.get("move") == 3:
            qp.setPen(QPen(QColor(30, 30, 30), 3))
            qp.setBrush(Qt.NoBrush)
            qp.drawArc(QRectF(hx - 12, hy - 13, 24, 24), 20 * 16, 140 * 16)
            qp.setBrush(QColor(220, 40, 40))
            qp.drawEllipse(QPointF(hx - 11, hy + 1), 3.5, 4.5)
            qp.drawEllipse(QPointF(hx + 11, hy + 1), 3.5, 4.5)
        if self.precip is not None and self.precip.kind in ("rain", "storm") and pose.upper[1] < -2.5:
            bx, by = at("hand_b")
            qp.setPen(QPen(QColor(40, 40, 40), 2))
            qp.drawLine(QPointF(bx, by + 4), QPointF(bx, by - 30))
            qp.setPen(QPen(OUTLINE, 1.5))
            qp.setBrush(QColor(40, 120, 230))
            path = QPainterPath()
            path.moveTo(bx - 36, by - 30)
            path.cubicTo(bx - 34, by - 62, bx + 34, by - 62, bx + 36, by - 30)
            path.closeSubpath()
            qp.drawPath(path)
        if self.soot > 0:
            qp.setPen(Qt.NoPen)
            for i in range(3):
                k = (t * 0.7 + i / 3) % 1.0
                qp.setBrush(QColor(90, 90, 90, int(150 * (1 - k))))
                qp.drawEllipse(QPointF(hx + math.sin(t * 2 + i * 2) * 8, hy - 18 - 30 * k), 4 + 5 * k, 4 + 5 * k)
            qp.setPen(QPen(QColor(120, 160, 60, 170), 1.5))
            for side in (-1, 1):
                x0 = hx + side * 18
                qp.drawLine(QPointF(x0, hy), QPointF(x0 + 3 * math.sin(t * 6), hy - 10))

    # ---- lifecycle
    def set_visible(self, vis):
        for w in self.fx + self.marks + self.minions + ([self.precip] if self.precip else []):
            w.setVisible(vis)
        if self.duel is not None:
            self.duel.hud.setVisible(vis)

    def release(self):
        d = self.d
        for w in self.fx + self.marks + self.minions + ([self.precip] if self.precip else []):
            w.kill()
        self.fx, self.marks, self.minions, self.precip = [], [], [], None
        if self.duel is not None:
            self.end_duel(None)
        if self.ha.active:
            self.ha.restore()
        if d.state == "sit" and self.goal.get("phase") == "sit":
            d.y = self.goal["top"]
        if d.state == "binned" and self.goal.get("rect"):
            r = self.goal["rect"]
            d.x, d.y = (r[0] + r[2]) / 2, r[1]
        self.goal = {}
        if d.state in STATES:
            d.on_ground = False
            d.set_state("idle", 1.0)
        self.save.write()
