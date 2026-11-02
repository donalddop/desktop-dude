"""The dude meets Cuttlefish Pet (github.com/donalddop/cuttlefish-pet).

When both run, they talk over Cuttlefish Pet's link pipe (request/answer, ~20x a second): the dude gets
every cuttlefish's position and mood, and sends back what he does to them. He rides one until it bucks him
off, carries one around and throws it, pets one, fights one (it inks back) or, rarely, eats one for real:
it goes in Cuttlefish Pet's graveyard as "opgegeten door de dude". Cuttlefish Pet refuses that when only
two are left. Without Cuttlefish Pet running none of this does anything.
"""

from __future__ import annotations

import dataclasses
import json
import math
import random
import threading
import time

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen

from arsenal import PopText
from life import pose_sit
from terror import LINES, _log
from warfare import OUTLINE, FxWindow, _painter

PIPE = r"\\.\pipe\CuttlefishPet.link"
BUSY = ("dudeheld", "dude-ride", "eaten", "dying")
SEAT = 18.0  # feet below the back so the sitting pose's hip (22 px up) sinks in a little

LINES.update({
    "aqua_ride": ["Yeehaw kanker!", "Hop inktvis, lopen!", "Rodeo, mattie!"],
    "aqua_thrown": ["Tering, ik lig eraf!", "Kankerbeest, rustig!", "Die vis is gestoord, wollah"],
    "aqua_carry": ["Kom maar mee, visje", "Gratis vlucht, wollah"],
    "aqua_throw": ["VLIEGENDE VIS!", "Doei inktvis!"],
    "aqua_pet": ["Rustig maar, visje", "Wie is er een brave inktvis?"],
    "aqua_petdone": ["Goed visje, wollah", "Oke, genoeg geknuffeld"],
    "aqua_fight": ["Kom dan, inktvis!", "1 tegen 1, sukkel!"],
    "aqua_win": ["Wie is de baas nu?", "Terug naar je aquarium, kanker"],
    "aqua_ink": ["INKT IN M'N BEK, KANKER!", "Ik zie niks, tering!"],
    "aqua_eat": ["Sushi time, mattie", "Verse inktvis, kankerlekker"],
    "aqua_refused": ["Nee, de laatsten laat ik leven", "Te weinig over, ik ben geen monster"],
    "aqua_lost": ["Kankerglibberig ding", "Weg is ie, tering"],
})


class Link:
    """Client side of Cuttlefish Pet's link pipe, on its own thread. Reconnects by itself."""

    def __init__(self, real):
        self.fish: dict[int, dict] = {}
        self.stamp = 0.0
        self.events: list = []
        self.pending: list = []
        self.dude = (0.0, 0.0, 0.0)
        self.connected = False
        self._lock = threading.Lock()
        if real:
            threading.Thread(target=self._loop, daemon=True).start()

    def send(self, op, replace=False):
        with self._lock:
            if replace:  # only the newest hold for a fish matters
                self.pending = [p for p in self.pending if not (p["op"] == op["op"] and p["id"] == op["id"])]
            self.pending.append(op)

    def take_events(self):
        with self._lock:
            ev, self.events = self.events, []
        return ev

    def _loop(self):
        while True:
            try:
                with open(PIPE, "r+b", buffering=0) as f:
                    self.connected = True
                    while True:
                        with self._lock:
                            ops, self.pending = self.pending, []
                        f.write((json.dumps({"ops": ops, "dude": list(self.dude)}) + "\n").encode())
                        buf = b""
                        while not buf.endswith(b"\n"):
                            chunk = f.read(65536)
                            if not chunk:
                                raise OSError("link closed")
                            buf += chunk
                        msg = json.loads(buf)
                        with self._lock:
                            self.fish = {x["id"]: x for x in msg.get("fish", [])}
                            self.stamp = time.monotonic()
                            self.events.extend(msg.get("events", []))
                        time.sleep(0.05)
            except (OSError, ValueError):
                pass
            if self.connected:
                _log("cuttlefish link lost")
            self.connected, self.fish = False, {}
            time.sleep(3.0)


class Heart(FxWindow):
    LIFE = 1.3

    def __init__(self, x, y):
        super().__init__(40, 40)
        self.x, self.y, self.age = x, y, 0.0
        self.place_at(x, y)
        self.show()

    def step(self, dt) -> bool:
        self.age += dt
        if self.age >= self.LIFE:
            self.kill()
            return False
        self.place_at(self.x + math.sin(self.age * 6) * 5, self.y - 40 * self.age)
        self.setWindowOpacity(max(0.0, 1 - self.age / self.LIFE))
        return True

    def paintEvent(self, _):
        qp = _painter(self)
        p = QPainterPath()
        p.moveTo(20, 32)
        p.cubicTo(2, 20, 6, 4, 20, 12)
        p.cubicTo(34, 4, 38, 20, 20, 32)
        qp.setPen(QPen(OUTLINE, 1.5))
        qp.setBrush(QColor(235, 50, 90))
        qp.drawPath(p)


class InkBlot(FxWindow):
    """Squirted in the face: a black splat that fades."""

    LIFE = 3.0

    def __init__(self, x, y):
        super().__init__(90, 90)
        self.place_at(x, y)
        self.age = 0.0
        self.blobs = [(random.uniform(-18, 18), random.uniform(-14, 14), random.uniform(7, 15)) for _ in range(8)]
        self.show()

    def step(self, dt) -> bool:
        self.age += dt
        if self.age >= self.LIFE:
            self.kill()
            return False
        if self.age > self.LIFE - 1:
            self.setWindowOpacity(max(0.0, self.LIFE - self.age))
        return True

    def paintEvent(self, _):
        qp = _painter(self)
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(15, 10, 25, 235))
        for dx, dy, r in self.blobs:
            qp.drawEllipse(QPointF(45 + dx, 45 + dy), r, r)


class Aquarium:
    MODES = ("ride", "carry", "pet", "fight", "eat")

    def __init__(self, dude, kit, real):
        self.d, self.kit, self.P = dude, kit, kit["Pose"]
        self.link = Link(real)
        self.enabled = True
        self.job: dict = {}
        self.fx: list = []
        self.cd, self.eat_cd, self.next_tray = 25.0, 240.0, 0.0
        self.stats = dict.fromkeys(self.MODES, 0)

    # ---- facts
    @property
    def FROZEN(self):
        return ("aqua",) if self.d.state == "aqua" and self.job.get("phase") == "ride" else ()

    def fish(self, fid):
        f = self.link.fish.get(fid)
        if f is None or f.get("beh") in ("eaten", "dying"):
            return None
        age = min(0.15, max(0.0, time.monotonic() - self.link.stamp)) if self.link.stamp else 0.0
        g = dict(f)
        # Cuttlefish Pet 2.9.1+ sends where the mantle top is; older ones only the sprite frame.
        g.setdefault("back", f["t"] + 0.45 * (f["bo"] - f["t"]))
        for a, b in (("x", "vx"), ("l", "vx"), ("r", "vx"), ("y", "vy"), ("t", "vy"), ("bo", "vy"),
                     ("back", "vy")):
            g[a] = g[a] + f[b] * age
        return g

    def candidates(self, mode):
        d = self.d
        out = []
        for fid in self.link.fish:
            f = self.fish(fid)
            if f is None or f.get("beh") in BUSY:
                continue
            if d.y - 330 <= f["y"] <= d.y + 30 and abs(f["x"] - d.x) < 900:
                out.append((abs(f["x"] - d.x) + abs(f["y"] - d.y) * 0.5, fid))
        return [fid for _, fid in sorted(out)]

    # ---- starting
    def pick_mode(self):
        d = self.d
        if d.rage >= 0.5:
            w = {"fight": 3, "carry": 2, "ride": 1, "eat": 1.5 if self.eat_cd <= 0 else 0, "pet": 0}
        else:
            w = {"pet": 3, "ride": 3, "carry": 2, "fight": 1, "eat": 0.3 if self.eat_cd <= 0 else 0}
        modes = [m for m in w if w[m] > 0]
        return random.choices(modes, weights=[w[m] for m in modes])[0]

    def start(self, mode, fid=None) -> bool:
        d = self.d
        if mode not in self.MODES or d.state in ("held", "ragdoll", "tanking", "binned", "aqua"):
            return False
        if fid is None:
            cands = self.candidates(mode)
            if not cands:
                return False
            fid = cands[0]
        self.job = {"mode": mode, "id": fid, "phase": "go", "t": 0.0, "n": 0, "k": 0.0, "until": 0.0}
        d.set_state("aqua", 99.0)
        d.terror.say("aqua_" + mode)
        self.cd = random.uniform(40, 90)
        return True

    # ---- per frame
    def think(self, dt, cur, btn) -> bool:
        d = self.d
        if d.state == "aqua":
            if not self.job:
                d.set_state("idle", 1.0)
            else:
                self.run(dt, cur, btn)
            return True
        if (self.enabled and self.cd <= 0 and not btn and d.on_ground and d.state in ("idle", "wander")
                and self.link.fish and d.life.duel is None and random.random() < 0.05 * dt):
            return self.start(self.pick_mode())
        return False

    def finish(self, line=None, state="idle"):
        d = self.d
        self.job = {}
        if line:
            d.terror.say(line)
        if d.state == "aqua":
            d.on_ground = False
            d.set_state(state, 1.2)

    def hold_point(self):
        d = self.d
        hx, hy = d.limb("hand_a", self.pose())
        if self.job["mode"] == "carry":
            hx2, hy2 = d.limb("hand_b", self.pose())
            return (hx + hx2) / 2, min(hy, hy2) - 22
        return hx + 14 * d.f, hy - 4

    def hold(self, fid):
        x, y = self.hold_point()
        self.link.send({"op": "hold", "id": fid, "x": x, "y": y, "f": self.d.f}, replace=True)

    def run(self, dt, cur, btn):
        d, j = self.d, self.job
        j["t"] += dt
        f = self.fish(j["id"])
        if f is None:
            self.finish("aqua_lost")
            return
        mode = j["mode"]
        if j["phase"] == "go":
            self.approach(dt, f)
            return
        dx = f["x"] - d.x
        if mode == "ride":
            self.run_ride(dt, f)
        elif mode == "carry":
            self.run_carry(dt, f)
        elif mode == "pet":
            d.vx = 0.0
            d.f = 1 if dx >= 0 else -1
            if abs(dx) > 90 or abs(f["y"] - d.y) > 220:
                j["phase"], j["t"] = "go", 0.0
            elif j["t"] >= j["until"]:
                if j["n"] >= 3:
                    self.stats["pet"] += 1
                    self.finish("aqua_petdone")
                    return
                j["n"] += 1
                j["until"] = j["t"] + 1.4
                self.link.send({"op": "pet", "id": j["id"]})
                self.fx.append(Heart(f["x"] + random.uniform(-15, 15), f["t"] - 10))
                d.rage = max(0.0, d.rage - 0.15)
        elif mode == "fight":
            d.vx = 0.0
            d.f = 1 if dx >= 0 else -1
            j["k"] = min(1.0, (j["t"]) / 0.38)
            if j["k"] >= 0.45 and not j.get("hit"):
                j["hit"] = True
                self.link.send({"op": "hit", "id": j["id"], "vx": 520 * d.f, "vy": -260})
                self.fx.append(PopText(f["x"], f["t"] - 20, "PATS!"))
                d.terror.sfx.play("bonk")
                j["n"] += 1
            if j["t"] > 0.6:
                if j["n"] >= 3:
                    self.stats["fight"] += 1
                    self.finish("aqua_win", "taunt")
                else:
                    j.update(phase="go", t=0.0, hit=False)
        elif mode == "eat":
            self.run_eat(dt, f)

    def approach(self, dt, f):
        d, j = self.d, self.job
        dx = f["x"] - d.x
        reach = abs(dx) < 50 and d.y - 200 < f["y"] < d.y + 30
        if reach and (d.on_ground or j["mode"] == "ride"):
            j.update(phase="act", t=0.0, k=0.0, until=0.0)
            d.vx = 0.0
            if j["mode"] == "ride":
                j["phase"] = "ride"
                self.link.send({"op": "ride", "id": j["id"], "secs": random.uniform(8, 14)})
            elif j["mode"] == "carry":
                j["until"] = random.uniform(2.5, 4.0)
                j["walk_to"] = d.world.clamp(d.x + random.uniform(-350, 350), d.y)[0]
            return
        if j["t"] > 9.0:
            self.finish("aqua_lost")
            return
        d.f = 1 if dx >= 0 else -1
        if abs(dx) > 25:
            d.walk(math.copysign(340, dx))
        else:
            d.vx = 0.0
        if d.on_ground and f["y"] < d.y - 90 and abs(dx) < 160:
            d.jump(-min(1150.0, 450 + (d.y - f["y"]) * 2.6))

    def run_ride(self, dt, f):
        d, j = self.d, self.job
        d.x, d.y = f["x"], f["back"] + SEAT  # hip on the mantle, legs either side
        d.vx, d.vy = f["vx"], f["vy"]
        d.on_ground, d.plat_hwnd = False, None
        d.f = 1 if f.get("right", True) else -1
        if f["beh"] == "dude-ride":
            j["riding"] = True
        elif j.get("riding") or j["t"] > 2.0:  # bucked off (or it never took off)
            self.stats["ride"] += 1 if j.get("riding") else 0
            self.job = {}
            d.vx, d.vy = f["vx"] * 0.8 + random.uniform(-200, 200), -750.0
            d.spin_v = random.choice((-9.0, 9.0))
            d.set_state("ragdoll")
            d.terror.say("aqua_thrown")
            return
        if j["t"] > 25:
            self.finish()

    def run_carry(self, dt, f):
        d, j = self.d, self.job
        if j["phase"] == "act":
            self.hold(j["id"])
            tx = j["walk_to"]
            if abs(tx - d.x) > 15 and j["t"] < j["until"]:
                d.walk(math.copysign(220, tx - d.x))
            else:
                d.vx = 0.0
            if j["t"] >= j["until"]:
                j["phase"], j["t"] = "throw", 0.0
                self.link.send({"op": "release", "id": j["id"], "vx": 950 * d.f, "vy": -550})
                d.terror.say("aqua_throw")
                d.terror.sfx.play("slash")
        elif j["t"] > 0.45:
            self.stats["carry"] += 1
            self.finish()

    def run_eat(self, dt, f):
        d, j = self.d, self.job
        d.vx = 0.0
        if j.get("sent"):
            if j["t"] > 4.0:  # no answer: give up
                self.finish()
            return
        self.hold(j["id"])
        if j["t"] >= j["until"]:
            if j["n"] >= 4:
                j["sent"], j["t"] = True, 0.0
                self.link.send({"op": "eat", "id": j["id"]})
                return
            j["n"] += 1
            j["until"] = j["t"] + 0.7
            if j["n"] > 1:
                x, y = self.hold_point()
                self.fx.append(PopText(x, y - 30, "HAP!"))
                d.terror.sfx.play("chomp")

    def step(self, dt, cur, btn):
        d = self.d
        self.cd -= dt
        self.eat_cd -= dt
        self.link.dude = (d.x, d.y - 50, d.rage)
        if self.job and d.state != "aqua":  # punched, thrown, paused: let go of whatever he had
            if self.job.get("mode") in ("carry", "eat") and self.job.get("phase") == "act":
                self.link.send({"op": "release", "id": self.job["id"], "vx": d.vx, "vy": d.vy})
            self.job = {}
        for ev in self.link.take_events():
            self.on_event(ev)
        self.fx = [w for w in self.fx if w.step(dt)]
        self.next_tray -= dt
        if self.next_tray <= 0:
            self.next_tray = 2.0
            a = getattr(getattr(d, "tray", None), "aqua_action", None)
            if a is not None:
                a.setText(f"Cuttlefish Pet: {len(self.link.fish)} zeekatten" if self.link.connected
                          else "Cuttlefish Pet: niet gevonden")

    def on_event(self, ev):
        d = self.d
        kind = ev.get("ev")
        if kind == "ink" and math.hypot(ev["x"] - d.x, ev["y"] - (d.y - 60)) < 170:
            hx, hy = d.limb("head")
            self.fx.append(InkBlot(hx, hy))
            d.terror.say("aqua_ink")
            if d.state not in ("held", "ragdoll", "binned"):
                self.job = {}
                d.vx = 0.0
                d.set_state("stunned", 1.5)
        elif kind == "eaten" and self.job.get("id") == ev.get("id"):
            self.stats["eat"] += 1
            self.eat_cd = 1200.0
            d.life.fish_eaten()
            d.terror.say("burp")
            d.terror.sfx.play("burp")
            self.finish(state="taunt")
        elif kind == "refused" and self.job.get("id") == ev.get("id"):
            self.link.send({"op": "release", "id": ev["id"], "vx": 0, "vy": 0})
            self.finish("aqua_refused")

    # ---- looks
    def pose(self):
        d, j, P = self.d, self.job, self.P
        if d.state != "aqua" or not j or j["phase"] == "go":
            return None
        mode, t = j["mode"], d.t
        if mode == "ride":
            p = pose_sit(P, t)
            w = math.sin(t * 8) * 0.3
            return dataclasses.replace(p, upper=(2.7 + w, p.upper[1]), lower=(3.1 + w, p.lower[1]))
        if mode == "carry":
            base = self.kit["pose_walk"](t * 9, 0.4, 0.05, 0.3) if abs(d.vx) > 5 else self.kit["pose_stand"](t)
            if j["phase"] == "throw":
                return dataclasses.replace(base, lean=0.25, upper=(1.6, 1.4), lower=(1.5, 1.3))
            return dataclasses.replace(base, upper=(2.9, -2.9), lower=(3.15, -3.15))
        if mode == "pet":
            s = math.sin(t * 7)
            return dataclasses.replace(self.kit["pose_stand"](t), lean=0.18, upper=(1.0 + 0.25 * s, -0.2),
                                       lower=(1.5 + 0.3 * s, -0.3))
        if mode == "fight":
            return self.kit["pose_punch"](j["k"])
        if mode == "eat":
            return self.kit["pose_eat"](t)
        return None

    def paint(self, qp, ox, oy, pose, f):
        if self.d.state != "aqua" or self.job.get("phase") != "ride":
            return
        hx, hy = self.kit["skeleton"](pose, f)["head"]
        hx, hy = ox + hx, oy + hy
        qp.setPen(QPen(OUTLINE, 1.2))
        qp.setBrush(QColor(140, 90, 40))
        qp.drawEllipse(QPointF(hx, hy - 9), 17, 4)  # cowboy hat brim
        qp.drawRoundedRect(hx - 8, hy - 21, 16, 12, 4, 4)

    # ---- lifecycle
    def set_visible(self, vis):
        for w in self.fx:
            w.setVisible(vis)

    def release(self):
        j = self.job
        if j and j.get("mode") in ("carry", "eat") and j.get("phase") == "act":
            self.link.send({"op": "release", "id": j["id"], "vx": 0, "vy": 0})
        for w in self.fx:
            w.kill()
        self.fx, self.job = [], {}
        if self.d.state == "aqua":
            self.d.set_state("idle", 1.0)
