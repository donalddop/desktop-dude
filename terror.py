"""Desktop terror: what the dude does to the rest of your desktop.

The rule: nothing is permanent. Screen damage is a screenshot *copy* in a click-through
overlay, windows always snap back (and he lets go the moment you hold a mouse button),
stolen icons are copies (the real icon never moves), and graffiti sticks until you click it.
"""

from __future__ import annotations

import math
import random
import sys
import threading
import time
import wave
from array import array
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)

import tuning
from appdir import DATA
from graffiti import Piece, paint_cached, render
from warfare import Blast, FxWindow, _painter

LOG = DATA / "desktop_dude.log"
STATES = ("spray", "surf", "flee", "hunt", "eat")

LINES = {
    "punched": ["Au kanker!", "Tering, m'n bek!", "Wollah, dat ga je voelen", "Is dat alles, sukkel?",
                "Ewa, rustig mattie!", "Kankerlijer, wacht maar"],
    "thrown": ["Ben je gek ofzo?!", "Tyfus, ik ben geen frisbee!", "WAAAH KANKERRR",
               "Wie gooit er nou mensen, eikel?!", "Dat vergeet ik niet, wollah"],
    "bored": ["Kankersaai hier", "Ewa, gebeurt er nog wat?", "Ik verveel me kapot",
              "Zal ik iets slopen? Ja toch", "Wat doe jij eigenlijk de hele dag, mattie?"],
    "steal": ["Dankjewel matje!", "Is nu van mij, wollah", "Kom het halen dan, sukkel", "Gejat, kankermakkelijk"],
    "drop": ["Oké oké, pak aan", "Pff, neem je kuticoon maar terug"],
    "graffiti": ["Kunst, tering!", "Even taggen", "Mooier zo toch?"],
    "surf": ["Yeehaw kanker!", "Raam-surfen, wollah", "Wheee!"],
    "glass": ["Oeps", "Ik was het niet, wollah", "Tering, glasschade"],
    "quake": ["AARDBEVING KANKER!", "Voel je dat, mattie?"],
    "blackout": ["Stroom is op, haha", "Wie doet het licht uit? Ik!", "Boe, sukkel!"],
    "hunt": ["Sushi, kankerlekker!", "Kom hier, inktvis!", "Ewa vis, blijf staan!"],
    "hunt_hit": ["Raak!", "Hebbes... bijna, tering"],
    "hunt_end": ["Kankergladde inktvis", "Volgende keer, vis"],
    "kill": ["DOOD, kanker!", "Inktvis down, wollah!", "Hebbes, tering!", "Rust zacht, sukkel"],
    "eat": ["Nom nom, kankerlekker", "Smaakt naar kip, wollah", "Beetje taai, tering", "Calamaris, mattie!"],
    "burp": ["BOEEEERP", "Pardon, mattie", "Kankervol", "Doe nog maar een, wollah"],
    "war": ["Nu is het oorlog, kanker!", "Luchtsteun komt eraan, mattie"],
    "boom": ["AU! Tyfus!", "Wie legt hier kankermijnen?!"],
    "tank_down": ["Mijn tank, kanker!!", "Die was nieuw, godverdomme!"],
    "bat": ["Batter up, kanker!", "Home run, mattie!", "Knuppeltje voor je, sukkel"],
    "golf": ["FORE, sukkel!", "Hole in one, tering!", "Ewa, even een balletje slaan"],
    "pan": ["Ik bak je, tering!", "Pannenkoek van je maken, wollah"],
    "haring": ["Hollandse Nieuwe in je bek!", "Vis voor je smoel, kanker!", "Met uitjes, mattie?"],
    "chainsaw": ["VRRRAAAH KANKER!", "Even snoeien, sukkel", "Texas Amsterdam massacre, wollah"],
    "chicken": ["Pok pok, kanker!", "Kip in je bek, mattie", "Dit is een serieus wapen, tering"],
    "pistol": ["Pew pew, sukkel", "Handen omhoog, kankercursor!"],
    "mg": ["RATATATA KANKER!", "Zeg maar dag tegen je bureaublad, mattie!"],
    "shotgun": ["Ka-tsjak! Kom dan!", "Hagel in je bek, sukkel"],
    "sniper": ["Rode stip, je bent dood", "Niet bewegen, kankercursor...", "Ik zie je wel, mattie"],
    "grenade": ["Granaat! Rennen, kanker!", "Vang!", "Pin eruit, wollah"],
    "dynamite": ["3... 2... tering!", "Wegwezen, mattie!", "Dit wordt kankergroot"],
    "pie": ["Slagroom in je bek!", "Taartje? Van mij, sukkel", "Gefeliciteerd, kanker!"],
    "boomerang": ["Komt altijd terug, net als ik", "Boemerang, kanker!", "Duik, mattie!"],
}
POPUPS = [
    "dude.exe heeft je cursor opgegeten.",
    "Fout 0xD00D: te weinig respect gedetecteerd.",
    "Je bureaublad is overgenomen. Druk op OK om je over te geven.",
    "Waarschuwing: inktvis gedetecteerd op je scherm.",
    "Er zit een poppetje in je systeem. Dit is normaal.",
]
TAGS = ["DUDE WAS HIER", "BOEM!", "LOL", "NOOB", "KOM DAN", "MIJN SCHERM", "ZWAKKE CURSOR", "CHAOS",
        "OEPS", "XD", "TERING", "EWA", "WOLLAH"]
NEON = [(255, 60, 170), (60, 230, 120), (60, 200, 255), (255, 210, 40), (255, 110, 40), (180, 90, 255)]
TERROR_MENU = [
    ("glass", "Glass break"),
    ("quake", "Earthquake"),
    ("blackout", "Power cut"),
    ("graffiti", "Graffiti"),
    ("steal", "Steal an icon"),
    ("surf", "Window surfing"),
    ("popup", "Fake error"),
    ("hunt", "Hunt the cuttlefish"),
]


def _log(msg):
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} terror: {msg}\n")
    except OSError:
        pass


def grab(x, y, w, h) -> QPixmap:
    """Screenshot of a screen region (falls back to a grey block where grabbing isn't possible)."""
    w, h = max(1, int(w)), max(1, int(h))
    pm = None
    try:
        scr = QGuiApplication.screenAt(QPoint(int(x + w / 2), int(y + h / 2))) or QGuiApplication.primaryScreen()
        g = scr.geometry()
        pm = scr.grabWindow(0, int(x - g.x()), int(y - g.y()), w, h)
    except Exception:  # noqa: BLE001 - a failed grab must not kill the effect
        pm = None
    if pm is None or pm.isNull() or pm.width() < w // 2:
        pm = QPixmap(w, h)
        pm.fill(QColor(70, 80, 95))
    return pm


def _ease(k):
    return 1 - (1 - k) ** 3


def _lerp(a, b, e):
    return (a[0] + (b[0] - a[0]) * e, a[1] + (b[1] - a[1]) * e)


# --------------------------------------------------------------------------- sound

SR = 22050


def _noise_lp(n, coef):
    out, lp = [], 0.0
    for _ in range(n):
        lp += (random.uniform(-1, 1) - lp) * coef
        out.append(lp)
    return out


def _s_boom():
    n = int(0.7 * SR)
    lp = _noise_lp(n, 0.08)
    return [(lp[i] * 3 + 0.7 * math.sin(2 * math.pi * 55 * i / SR)) * math.exp(-i / SR * 5) for i in range(n)]


def _s_shot():
    return [random.uniform(-1, 1) * math.exp(-i / SR * 70) for i in range(int(0.07 * SR))]


def _s_fire():
    out, lp = [], 0.0
    for i in range(int(0.4 * SR)):
        t = i / SR
        lp += (random.uniform(-1, 1) - lp) * (0.04 + 0.4 * t)
        out.append(lp * min(1.0, t * 40) * math.exp(-t * 5) + 0.8 * math.sin(2 * math.pi * 80 * t) * math.exp(-t * 25))
    return out


def _s_slash():
    out, lp = [], 0.0
    for i in range(int(0.2 * SR)):
        x = random.uniform(-1, 1)
        lp += (x - lp) * 0.3
        out.append((x - lp) * math.sin(math.pi * i / SR / 0.2))
    return out


def _s_clang():
    parts = ((880, 6), (1310, 8), (1960, 10), (2770, 14))
    return [
        sum(math.sin(2 * math.pi * f * i / SR) * math.exp(-i / SR * d) for f, d in parts)
        for i in range(int(0.6 * SR))
    ]


def _s_ugh():
    out, ph, lp = [], 0.0, 0.0
    for i in range(int(0.28 * SR)):
        t = i / SR
        ph += (150 - 230 * t) / SR
        lp += (2 * (ph % 1) - 1 - lp) * 0.15
        out.append(lp * math.sin(math.pi * t / 0.28))
    return out


def _s_glass():
    n = int(0.8 * SR)
    out = [0.0] * n
    burst = int(0.05 * SR)
    for i in range(burst):
        out[i] += random.uniform(-1, 1) * (1 - i / burst)
    for _ in range(14):
        s, f = random.randint(0, n // 2), random.uniform(2200, 5200)
        for i in range(s, min(n, s + int(0.25 * SR))):
            t = (i - s) / SR
            out[i] += 0.35 * math.sin(2 * math.pi * f * t) * math.exp(-t * 18)
    return out


def _s_rumble():
    n = int(1.6 * SR)
    lp = _noise_lp(n, 0.02)
    return [lp[i] * math.sin(math.pi * i / n) for i in range(n)]


def _s_spray():
    out, lp = [], 0.0
    for i in range(int(0.9 * SR)):
        t, x = i / SR, random.uniform(-1, 1)
        lp += (x - lp) * 0.5
        out.append((x - lp) * min(1.0, t * 20, (0.9 - t) * 10))
    return out


def _s_power():
    out, ph = [], 0.0
    for i in range(int(0.9 * SR)):
        t = i / SR
        ph += (140 - 120 * t / 0.9) / SR
        out.append((math.sin(2 * math.pi * ph) + 0.3 * (2 * (ph % 1) - 1)) * math.exp(-t * 2.5))
    return out


def _s_yoink():
    out, ph = [], 0.0
    for i in range(int(0.18 * SR)):
        t = i / SR
        ph += 300 * (1400 / 300) ** (t / 0.18) / SR
        out.append(math.sin(2 * math.pi * ph) * math.sin(math.pi * t / 0.18))
    return out


def _s_ding():
    return [
        (math.sin(2 * math.pi * 880 * i / SR) + 0.6 * math.sin(2 * math.pi * 1320 * i / SR)) * math.exp(-i / SR * 7)
        for i in range(int(0.5 * SR))
    ]


def _s_bonk():
    out, ph = [], 0.0
    for i in range(int(0.25 * SR)):
        t = i / SR
        ph += 2 * math.pi * (430 - 600 * t) / SR
        out.append(0.9 * math.sin(ph) * math.exp(-t * 20) + random.uniform(-1, 1) * 0.6 * math.exp(-t * 300))
    return out


def _s_squeak():
    out, ph, dur = [], 0.0, 0.35
    for i in range(int(dur * SR)):
        t = i / SR
        ph += 2 * math.pi * (1100 + 500 * math.sin(math.pi * t / dur) + 60 * math.sin(2 * math.pi * 28 * t)) / SR
        out.append((0.6 * math.sin(ph) + 0.3 * math.sin(2 * ph)) * min(1.0, t * 60) * (1 - t / dur))
    return out


def _s_splat():
    n = int(0.3 * SR)
    lp = _noise_lp(n, 0.25)
    return [(lp[i] * 2.5 + 0.7 * math.sin(2 * math.pi * 90 * i / SR) * math.exp(-i / SR * 30))
            * math.exp(-i / SR * 14) for i in range(n)]


def _s_saw():
    out, ph = [], 0.0
    for i in range(int(1.0 * SR)):
        t = i / SR
        ph += (95 + 25 * math.sin(2 * math.pi * 7 * t)) / SR
        buzz = 2 * (ph % 1.0) - 1 + random.uniform(-0.3, 0.3)
        out.append(0.6 * buzz * min(1.0, t * 20) * min(1.0, (1 - t) * 8))
    return out


def _s_chomp():
    n = int(0.16 * SR)
    lp = _noise_lp(n, 0.5)
    return [(lp[i] * 2.2 * (1 if (i // 300) % 2 else 0.4) + 0.5 * math.sin(2 * math.pi * 120 * i / SR))
            * math.exp(-i / SR * 18) for i in range(n)]


def _s_burp():
    out, ph, dur = [], 0.0, 0.7
    for i in range(int(dur * SR)):
        t = i / SR
        ph += (85 - 25 * t + 8 * math.sin(2 * math.pi * 23 * t)) / SR
        saw = 2 * (ph % 1.0) - 1
        out.append(0.8 * saw * (0.6 + 0.4 * math.sin(2 * math.pi * 31 * t)) * min(1.0, t * 30) * (1 - t / dur))
    return out


SOUNDS = {  # name: (generator, priority, duration, volume)
    "boom": (_s_boom, 3, 0.7, 0.9),
    "glass": (_s_glass, 3, 0.8, 0.7),
    "rumble": (_s_rumble, 3, 1.6, 0.9),
    "power": (_s_power, 3, 0.9, 0.7),
    "fire": (_s_fire, 2, 0.4, 0.8),
    "clang": (_s_clang, 2, 0.6, 0.6),
    "ugh": (_s_ugh, 2, 0.28, 0.8),
    "yoink": (_s_yoink, 2, 0.18, 0.5),
    "ding": (_s_ding, 2, 0.5, 0.5),
    "slash": (_s_slash, 1, 0.2, 0.6),
    "spray": (_s_spray, 1, 0.9, 0.35),
    "shot": (_s_shot, 0, 0.07, 0.4),
    "bonk": (_s_bonk, 2, 0.25, 0.8),
    "squeak": (_s_squeak, 2, 0.35, 0.6),
    "splat": (_s_splat, 2, 0.3, 0.8),
    "saw": (_s_saw, 2, 1.0, 0.6),
    "chomp": (_s_chomp, 2, 0.16, 0.7),
    "burp": (_s_burp, 3, 0.7, 0.8),
}


class Sfx:
    """Procedurally generated sound effects (cached as small wav files), played async."""

    def __init__(self, enabled, folder: Path):
        self.muted = True  # off by default: tray > Sound to turn it on
        self.enabled = enabled and sys.platform in ("win32", "darwin")
        self.files: dict[str, str] = {}
        self.last: dict[str, float] = {}
        self.busy_until, self.busy_prio = 0.0, 0
        if not self.enabled:
            return
        try:
            folder.mkdir(exist_ok=True)
            for name, (gen, _prio, _dur, vol) in SOUNDS.items():
                path = folder / f"{name}_v1.wav"
                if not path.exists():
                    xs = gen()
                    peak = max(1e-6, max(abs(v) for v in xs))
                    data = array("h", (int(max(-1.0, min(1.0, v / peak * vol)) * 30000) for v in xs))
                    with wave.open(str(path), "wb") as w:
                        w.setnchannels(1)
                        w.setsampwidth(2)
                        w.setframerate(SR)
                        w.writeframes(data.tobytes())
                self.files[name] = str(path)
        except Exception as e:  # noqa: BLE001 - no sound is fine, no dude is not
            _log(f"sound disabled: {e!r}")
            self.enabled = False

    def play(self, name):
        if not self.enabled or self.muted or name not in self.files:
            return
        _gen, prio, dur, _vol = SOUNDS[name]
        now = time.monotonic()
        if (now < self.busy_until and prio < self.busy_prio) or now - self.last.get(name, 0.0) < 0.12:
            return
        self.last[name] = now
        try:
            if sys.platform == "darwin":
                import subprocess

                subprocess.Popen(["afplay", self.files[name]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                import winsound

                winsound.PlaySound(self.files[name], winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except (RuntimeError, OSError):
            return
        self.busy_until, self.busy_prio = now + dur, prio


# --------------------------------------------------------------------------- desktop probe


class FakeProbe:
    def __init__(self):
        self.icons: list = []  # (name, (l, t, r, b))
        self.fish: list = []  # (cx, cy, w, h)

    def request(self, what):
        pass

    def stop(self):
        pass


class Probe(FakeProbe):
    """Reads desktop icon and cuttlefish positions via UI Automation, in a background thread."""

    def __init__(self):
        super().__init__()
        self._want: set[str] = {"icons", "fish"}
        self._ev = threading.Event()
        self._alive = True
        threading.Thread(target=self._run, daemon=True).start()
        self._ev.set()

    def request(self, what):
        self._want.add(what)
        self._ev.set()

    def stop(self):
        self._alive = False
        self._ev.set()

    def _run(self):
        try:
            import ctypes
            from ctypes import wintypes as wt

            import comtypes
            import comtypes.client

            comtypes.CoInitialize()
            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen.UIAutomationClient import (
                CUIAutomation,
                IUIAutomation,
                TreeScope_Children,
                TreeScope_Descendants,
            )

            uia = comtypes.client.CreateObject(CUIAutomation, interface=IUIAutomation)
            cond = uia.CreateTrueCondition()
            u = ctypes.WinDLL("user32")
            u.FindWindowW.restype = wt.HWND
            u.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
            u.FindWindowExW.restype = wt.HWND
            u.FindWindowExW.argtypes = [wt.HWND, wt.HWND, wt.LPCWSTR, wt.LPCWSTR]
            u.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
            enum_proc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
            u.EnumWindows.argtypes = [enum_proc, wt.LPARAM]
        except Exception as e:  # noqa: BLE001
            _log(f"probe disabled: {e!r}")
            return

        def listview():
            def lv_of(top):
                dv = u.FindWindowExW(top, None, "SHELLDLL_DefView", None)
                return u.FindWindowExW(dv, None, "SysListView32", None) if dv else None

            lv = lv_of(u.FindWindowW("Progman", None))
            h = None
            while not lv:
                h = u.FindWindowExW(None, h, "WorkerW", None)
                if not h:
                    break
                lv = lv_of(h)
            return lv

        def icons():
            lv = listview()
            if not lv:
                return []
            items = uia.ElementFromHandle(lv).FindAll(TreeScope_Children, cond)
            out = []
            for i in range(items.Length):
                it = items.GetElement(i)
                r = it.CurrentBoundingRectangle
                if r.right > r.left and r.bottom > r.top:
                    out.append((it.CurrentName, (r.left, r.top, r.right, r.bottom)))
            return out

        def fish():
            found = []

            def cb(h, _):
                buf = ctypes.create_unicode_buffer(128)
                u.GetClassNameW(h, buf, 128)
                if buf.value.startswith("HwndWrapper[CuttlefishPet"):
                    found.append(h)
                return True

            u.EnumWindows(enum_proc(cb), 0)
            out, seen = [], set()
            for h in found:
                items = uia.ElementFromHandle(h).FindAll(TreeScope_Descendants, cond)
                for i in range(items.Length):
                    r = items.GetElement(i).CurrentBoundingRectangle
                    w, hh = r.right - r.left, r.bottom - r.top
                    if not (18 <= w <= 220 and 14 <= hh <= 220):
                        continue
                    cx, cy = (r.left + r.right) / 2, (r.top + r.bottom) / 2
                    key = (round(cx / 12), round(cy / 12))
                    if key not in seen:
                        seen.add(key)
                        out.append((cx, cy, w, hh))
            return out

        last = 0.0
        while self._alive:
            self._ev.wait(timeout=10.0)
            self._ev.clear()
            want, self._want = self._want, set()
            if time.monotonic() - last > 10.0:
                want |= {"icons", "fish"}
                last = time.monotonic()
            for what in want:
                try:
                    if what == "icons":
                        self.icons = icons()
                    elif what == "fish":
                        self.fish = fish()
                except Exception as e:  # noqa: BLE001 - explorer restarts, pet closed, ...
                    _log(f"probe {what}: {e!r}")


# --------------------------------------------------------------------------- overlays


class Shatter(FxWindow):
    """A screenshot copy of a screen patch cracks, then falls apart in shards."""

    CRACK, LIFE, M = 0.45, 3.4, 140

    def __init__(self, x, y, w, h, ix, iy, floor):
        super().__init__(int(w + 2 * self.M), int(max(floor - y, h + 10)))
        self.move(round(x - self.M), round(y))
        self.pm = grab(x, y, w, h)
        self.age = 0.0
        cols, rows = 5, 4
        cw, ch = w / cols, h / rows
        grid = {}
        for i in range(cols + 1):
            for j in range(rows + 1):
                px, py = i * cw, j * ch
                if 0 < i < cols:
                    px += random.uniform(-0.3, 0.3) * cw
                if 0 < j < rows:
                    py += random.uniform(-0.3, 0.3) * ch
                grid[i, j] = (px, py)
        self.shards = []
        for i in range(cols):
            for j in range(rows):
                a, b, c, d = grid[i, j], grid[i + 1, j], grid[i + 1, j + 1], grid[i, j + 1]
                tris = [(a, b, c), (a, c, d)] if random.random() < 0.5 else [(a, b, d), (b, c, d)]
                for tri in tris:
                    cx, cy = sum(p[0] for p in tri) / 3, sum(p[1] for p in tri) / 3
                    away = math.atan2(cy - iy, cx - ix)
                    poly = QPolygonF([QPointF(*p) for p in tri])
                    path = QPainterPath()
                    path.addPolygon(poly)
                    path.closeSubpath()
                    self.shards.append({
                        "poly": poly, "path": path, "cx": cx, "cy": cy,
                        "delay": math.hypot(cx - ix, cy - iy) / max(w, h) * 0.35,
                        "vx": math.cos(away) * random.uniform(40, 160), "vy": random.uniform(-180, -40),
                        "spin": random.uniform(-260, 260), "ox": 0.0, "oy": 0.0, "rot": 0.0,
                    })
        self.cracks = []
        for _ in range(7):
            ang, px, py = random.uniform(0, math.tau), ix, iy
            pts = [QPointF(px, py)]
            for _ in range(5):
                ang += random.uniform(-0.4, 0.4)
                step = random.uniform(15, 35)
                px, py = px + math.cos(ang) * step, py + math.sin(ang) * step
                pts.append(QPointF(px, py))
            self.cracks.append(QPolygonF(pts))
        self.show()

    def step(self, dt) -> bool:
        self.age += dt
        if self.age >= self.LIFE:
            self.kill()
            return False
        t = self.age - self.CRACK
        if t > 0:
            for s in self.shards:
                if t >= s["delay"]:
                    s["vy"] += 2200 * dt
                    s["ox"] += s["vx"] * dt
                    s["oy"] += s["vy"] * dt
                    s["rot"] += s["spin"] * dt
        self.update()
        return True

    def paintEvent(self, _):
        qp = _painter(self)
        m = self.M
        if self.age < self.CRACK:
            qp.drawPixmap(m, 0, self.pm)
            qp.translate(m, 0)
            for w, col in ((3.0, QColor(255, 255, 255, 190)), (1.2, QColor(20, 20, 20, 220))):
                qp.setPen(QPen(col, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                for poly in self.cracks:
                    qp.drawPolyline(poly)
            return
        t = self.age - self.CRACK
        void = max(0.0, 1 - t / (self.LIFE - self.CRACK - 0.3))
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(8, 8, 10, int(235 * void)))
        for s in self.shards:
            if t >= s["delay"]:
                qp.drawPolygon(s["poly"].translated(m, 0))
        qp.setOpacity(max(0.0, min(1.0, (self.LIFE - self.age) / 0.6)))
        for s in self.shards:
            qp.save()
            qp.translate(m + s["cx"] + s["ox"], s["cy"] + s["oy"])
            qp.rotate(s["rot"])
            qp.translate(-s["cx"], -s["cy"])
            qp.setClipPath(s["path"])
            qp.drawPixmap(0, 0, self.pm)
            qp.setClipping(False)
            qp.setPen(QPen(QColor(255, 255, 255, 150), 1.2))
            qp.setBrush(Qt.NoBrush)
            qp.drawPath(s["path"])
            qp.restore()


class Quake(FxWindow):
    """The whole screen (a copy of it) shakes."""

    LIFE = 2.0

    def __init__(self, geom):
        super().__init__(geom.width(), geom.height())
        self.move(geom.x(), geom.y())
        self.pm = grab(geom.x(), geom.y(), geom.width(), geom.height())
        self.age, self.off = 0.0, (0.0, 0.0, 0.0)
        self.show()

    def step(self, dt) -> bool:
        self.age += dt
        if self.age >= self.LIFE:
            self.kill()
            return False
        a = 22 * (1 - self.age / self.LIFE) ** 1.3
        self.off = (random.uniform(-a, a), random.uniform(-a * 0.6, a * 0.6), random.uniform(-0.5, 0.5) * a / 22)
        self.update()
        return True

    def paintEvent(self, _):
        qp = _painter(self)
        qp.fillRect(self.rect(), QColor(10, 10, 12))
        dx, dy, rot = self.off
        qp.translate(self.w_ / 2 + dx, self.h_ / 2 + dy)
        qp.rotate(rot)
        qp.translate(-self.w_ / 2, -self.h_ / 2)
        qp.drawPixmap(0, 0, self.pm)


class Blackout(FxWindow):
    """Power cut: darkness with a flashlight around your cursor."""

    LIFE = 8.0

    def __init__(self, geom, cursor):
        super().__init__(geom.width(), geom.height())
        self.move(geom.x(), geom.y())
        self.ox, self.oy = geom.x(), geom.y()
        self.cursor, self.age, self.last = cursor, 0.0, None
        self.show()

    def level(self):
        a = self.age
        if a < 0.5:
            return 1.0 if int(a * 14) % 2 == 0 else 0.35
        if a > self.LIFE - 0.8:
            return 0.4 if int(a * 14) % 2 else 0.0
        return 1.0

    def step(self, dt) -> bool:
        self.age += dt
        if self.age >= self.LIFE:
            self.kill()
            return False
        key = (self.cursor(), self.level())
        if key != self.last:
            self.last = key
            self.update()
        return True

    def paintEvent(self, _):
        lvl = self.level()
        if lvl <= 0:
            return
        qp = _painter(self)
        cx, cy = self.cursor()
        g = QRadialGradient(QPointF(cx - self.ox, cy - self.oy), 170)
        g.setColorAt(0.0, QColor(0, 0, 0, 0))
        g.setColorAt(0.55, QColor(0, 0, 0, int(60 * lvl)))
        g.setColorAt(1.0, QColor(0, 0, 0, int(245 * lvl)))
        qp.fillRect(self.rect(), QBrush(g))


class Graffiti(FxWindow):
    """Spray piece on top of everything, high up on the screen (when there's no bare wallpaper to be had).
    Sticks until you click it."""

    def __init__(self, x, y, piece=None, auto=True):
        self.auto = auto  # False: the dude sprays it on himself (vandal.py drives the progress)
        self.piece = piece or Piece(random.choice(("tag", "throwup", "throwup")), scale=0.8)
        self.W, self.H = self.piece.size()
        super().__init__(self.W, self.H, clickable=True)
        self.place_at(x, y)
        self.progress, self.fading, self.img, self.erase = 0.0, None, None, 0.0
        self.show()

    def set_image(self, img):
        self.img = img
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.fading is None:
            self.fading = 0.0

    def set_progress(self, k):
        self.progress = k
        self.update()

    def step(self, dt) -> bool:
        if self.auto and self.progress < 1.0:
            self.progress = min(1.0, self.progress + dt / 1.3)
            self.update()
        if self.fading is not None:
            self.fading += dt
            if self.fading >= 0.35:
                self.kill()
                return False
            self.setWindowOpacity(1 - self.fading / 0.35)
        return True

    def paintEvent(self, _):
        if self.img is None and (self.auto or self.progress >= 1.0):
            self.img = render(self.piece)  # nobody pre-rendered it: do it now (once)
        paint_cached(QPainter(self), self.W, self.H, self.piece, self.img, self.progress, erase=self.erase)


class Bubble(FxWindow):
    """Speech bubble above his head. Big and readable, wraps long lines."""

    LIFE, MAXW = 3.4, 380

    def __init__(self, text):
        font = QFont("Segoe UI")
        font.setPixelSize(22)
        font.setBold(True)
        flags = int(Qt.AlignCenter) | int(Qt.TextWordWrap)
        br = QFontMetrics(font).boundingRect(0, 0, self.MAXW, 1000, flags, text)
        super().__init__(br.width() + 40, br.height() + 36)
        self.text, self.font_, self.flags, self.age = text, font, flags, 0.0
        self.show()

    def follow(self, x, y):
        self.move(round(x - self.w_ / 2), round(y - self.h_))

    def step(self, dt) -> bool:
        self.age += dt
        if self.age >= self.LIFE:
            self.kill()
            return False
        if self.age > self.LIFE - 0.4:
            self.setWindowOpacity(max(0.0, (self.LIFE - self.age) / 0.4))
        return True

    def paintEvent(self, _):
        qp = _painter(self)
        qp.setPen(QPen(QColor(25, 25, 25), 3))
        qp.setBrush(QColor(255, 255, 255, 250))
        body = QRectF(2, 2, self.w_ - 4, self.h_ - 16)
        qp.drawRoundedRect(body, 16, 16)
        cx = self.w_ / 2
        qp.drawPolygon(QPolygonF([QPointF(cx - 9, body.bottom() - 1), QPointF(cx, self.h_ - 2),
                                  QPointF(cx + 9, body.bottom() - 1)]))
        qp.setPen(Qt.NoPen)
        qp.drawRect(QRectF(cx - 8, body.bottom() - 4, 16, 4))
        qp.setPen(QColor(20, 20, 20))
        qp.setFont(self.font_)
        qp.drawText(body, self.flags, self.text)


class ErrorPopup(FxWindow):
    """Obviously fake 'dude.exe' error. Click to close; it never steals focus."""

    W, H, LIFE = 380, 150, 8.0

    def __init__(self, x, y, msg):
        super().__init__(self.W, self.H, clickable=True)
        self.place_at(x, y)
        self.msg, self.age, self.closing = msg, 0.0, False
        self.show()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.closing = True

    def step(self, dt) -> bool:
        self.age += dt
        if self.closing or self.age >= self.LIFE:
            self.kill()
            return False
        return True

    def paintEvent(self, _):
        qp = _painter(self)
        w, h = self.W, self.H
        qp.setPen(QPen(QColor(40, 40, 40), 2))
        qp.setBrush(QColor(246, 246, 246))
        qp.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 8, 8)
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(200, 40, 40))
        qp.drawRoundedRect(QRectF(1, 1, w - 2, 30), 8, 8)
        qp.drawRect(QRectF(1, 18, w - 2, 13))
        qp.setPen(QPen(QColor(255, 255, 255), 2, Qt.SolidLine, Qt.RoundCap))  # tiny stick figure
        qp.setBrush(Qt.NoBrush)
        qp.drawEllipse(QPointF(18, 10), 3.5, 3.5)
        qp.drawLine(QPointF(18, 14), QPointF(18, 21))
        qp.drawLine(QPointF(18, 21), QPointF(14, 27))
        qp.drawLine(QPointF(18, 21), QPointF(22, 27))
        qp.drawLine(QPointF(13, 16), QPointF(23, 16))
        f = QFont("Segoe UI")
        f.setPixelSize(14)
        f.setBold(True)
        qp.setFont(f)
        qp.setPen(QColor(255, 255, 255))
        qp.drawText(QRectF(34, 1, w - 80, 30), int(Qt.AlignVCenter) | int(Qt.AlignLeft), "dude.exe")
        qp.drawText(QRectF(w - 32, 1, 26, 30), int(Qt.AlignCenter), "x")
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(210, 40, 40))
        qp.drawEllipse(QPointF(40, 72), 18, 18)
        qp.setPen(QColor(255, 255, 255))
        f.setPixelSize(24)
        qp.setFont(f)
        qp.drawText(QRectF(22, 54, 36, 36), int(Qt.AlignCenter), "!")
        f.setPixelSize(14)
        f.setBold(False)
        qp.setFont(f)
        qp.setPen(QColor(30, 30, 30))
        qp.drawText(QRectF(72, 40, w - 88, 64), int(Qt.AlignVCenter) | int(Qt.AlignLeft) | int(Qt.TextWordWrap), self.msg)
        qp.setPen(QPen(QColor(90, 90, 90), 1.5))
        qp.setBrush(QColor(225, 225, 225))
        ok = QRectF(w - 96, h - 38, 80, 26)
        qp.drawRoundedRect(ok, 4, 4)
        qp.setPen(QColor(20, 20, 20))
        qp.drawText(ok, int(Qt.AlignCenter), "OK")


class Stolen(FxWindow):
    """Placeholder covering a kidnapped icon. Click-through, so the real icon still works."""

    def __init__(self, x, y, w, h, bg):
        super().__init__(int(w), int(h))
        self.move(round(x), round(y))
        self.bg = bg
        self.show()

    def paintEvent(self, _):
        qp = _painter(self)
        qp.fillRect(self.rect(), self.bg)
        qp.setPen(QPen(QColor(255, 255, 255, 200), 1.5, Qt.DashLine))
        qp.setBrush(Qt.NoBrush)
        qp.drawRoundedRect(QRectF(3, 3, self.w_ - 6, self.h_ - 6), 4, 4)
        f = QFont("Segoe UI")
        f.setPixelSize(11)
        f.setBold(True)
        qp.setFont(f)
        qp.setPen(QColor(255, 70, 70))
        qp.drawText(QRectF(0, 0, self.w_, self.h_), int(Qt.AlignCenter), "GESTOLEN")


class IconCopy(FxWindow):
    def __init__(self, pm):
        super().__init__(pm.width() + 8, pm.height() + 8)
        self.pm = pm
        self.show()

    def paintEvent(self, _):
        _painter(self).drawPixmap(4, 4, self.pm)


class Splash(FxWindow):
    """Fish hit: bubbles and stars."""

    LIFE = 0.8

    def __init__(self, x, y):
        super().__init__(110, 110)
        self.place_at(x, y)
        self.age = 0.0
        self.bubbles = [(random.uniform(-30, 30), random.uniform(40, 110), random.uniform(3, 8)) for _ in range(8)]
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
        a = int(230 * (1 - k))
        qp.setPen(QPen(QColor(170, 225, 255, a), 2))
        qp.setBrush(Qt.NoBrush)
        for dx, sp, r in self.bubbles:
            qp.drawEllipse(QPointF(55 + dx, 60 - sp * self.age), r, r)
        qp.setPen(QPen(QColor(255, 220, 60, a), 3, Qt.SolidLine, Qt.RoundCap))
        for i in range(6):
            ang = i * math.tau / 6
            r0, r1 = 8 + 30 * k, 16 + 40 * k
            qp.drawLine(QPointF(55 + math.cos(ang) * r0, 55 + math.sin(ang) * r0),
                        QPointF(55 + math.cos(ang) * r1, 55 + math.sin(ang) * r1))


class DeadFish(FxWindow):
    """A cuttlefish he killed. A drawn one: the real ones in CuttlefishPet just swim on.
    Falls belly-up, then gets eaten bite by bite, or fades out if he never gets to it."""

    FADE = 7.0
    BITES = 4

    def __init__(self, tr, x, y, size):
        super().__init__(140, 140)
        self.tr, self.x, self.y = tr, x, y
        self.s = min(max(size, 40), 90) / 70
        self.vx, self.vy = random.uniform(-70, 70), -240.0
        self.rot, self.age, self.alone = 0.0, 0.0, 0.0
        self.landed = self.held = self.done = False
        self.bites = 0
        self.crumbs: list = []
        self.place_at(x, y)
        self.show()

    def bite(self):
        self.bites += 1
        bx = 70 + (30 - 15 * self.bites) * self.s
        for _ in range(7):
            self.crumbs.append([bx, 62.0, random.uniform(-70, 70), random.uniform(-160, -40), 0.0])

    def kill(self):
        self.done = True
        super().kill()

    def step(self, dt) -> bool:
        if self.done:
            return False
        self.age += dt
        if not self.held and not self.landed:
            world = self.tr.d.world
            prev = self.y
            self.vy += 1500 * dt
            self.x = min(max(self.x + self.vx * dt, world.left + 20), world.right - 20)
            self.y += self.vy * dt
            self.rot += 500 * dt * (1 if self.vx >= 0 else -1)
            ground = world.floor_at(self.x)
            for p in world.plats:
                if p.x1 <= self.x <= p.x2 and prev + 10 <= p.y <= self.y + 10 and p.y < ground:
                    ground = p.y
            if self.y >= ground - 10:
                self.y, self.landed, self.rot = ground - 10, True, 0.0
        if not self.held and self.landed:
            self.alone += dt
            if self.alone > self.FADE:
                self.kill()
                return False
            if self.alone > self.FADE - 1.0:
                self.setWindowOpacity(max(0.0, self.FADE - self.alone))
        for c in self.crumbs:
            c[3] += 900 * dt
            c[0] += c[2] * dt
            c[1] += c[3] * dt
            c[4] += dt
        self.crumbs = [c for c in self.crumbs if c[4] < 0.7]
        self.place_at(self.x, self.y)
        self.update()
        return True

    def paintEvent(self, _):
        qp = _painter(self)
        qp.save()
        qp.translate(70, 70)
        qp.rotate(self.rot)
        qp.scale(self.s, self.s)
        out = QColor(60, 30, 50)
        # tentacles, limp
        qp.setPen(QPen(QColor(190, 120, 150), 3, Qt.SolidLine, Qt.RoundCap))
        for i in range(4):
            y0 = -4 + i * 2.7
            qp.drawLine(QPointF(30, y0), QPointF(40 + i * 2, y0 + 7 + i * 2))
        # fin skirt + mantle (belly up: pale side on top)
        qp.setPen(QPen(out, 1.5))
        qp.setBrush(QColor(240, 200, 220))
        qp.drawEllipse(QPointF(-4, 0), 31, 16)
        qp.setBrush(QColor(200, 130, 165))
        qp.drawEllipse(QPointF(-4, 0), 26, 12)
        qp.setPen(QPen(QColor(150, 80, 115), 2, Qt.SolidLine, Qt.RoundCap))
        for sx in (-20, -11, -2, 7):
            qp.drawLine(QPointF(sx, 6), QPointF(sx + 4, 10))
        qp.setPen(QPen(out, 1.5))
        qp.setBrush(QColor(210, 145, 175))
        qp.drawEllipse(QPointF(24, 0), 10, 9)
        # X eyes
        qp.setPen(QPen(out, 2, Qt.SolidLine, Qt.RoundCap))
        for ex in (21, 28):
            qp.drawLine(QPointF(ex - 2.5, -5.5), QPointF(ex + 2.5, -0.5))
            qp.drawLine(QPointF(ex - 2.5, -0.5), QPointF(ex + 2.5, -5.5))
        # bite marks
        if self.bites:
            qp.setCompositionMode(type(qp).CompositionMode_Clear)
            qp.setPen(Qt.NoPen)
            qp.setBrush(QColor(0, 0, 0))
            for i in range(1, self.bites + 1):
                bx = 30 - 15 * i
                qp.drawEllipse(QPointF(bx, -9 + (i % 2) * 4), 11, 11)
                qp.drawEllipse(QPointF(bx + 6, -6), 8, 8)
            qp.setCompositionMode(type(qp).CompositionMode_SourceOver)
        qp.restore()
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(200, 130, 165))
        for x, y, _vx, _vy, _a in self.crumbs:
            qp.drawEllipse(QPointF(x, y), 2.2, 2.2)


# --------------------------------------------------------------------------- the terror itself


class Terror:
    FROZEN = ("surf",)

    def __init__(self, dude, real):
        self.d = dude
        self.enabled = True
        self.probe = Probe() if real and sys.platform == "win32" else FakeProbe()  # UI Automation
        self.sfx = Sfx(real, DATA / "sounds")
        self.graffiti: list[Graffiti] = []
        self.fx: list = []
        self.pending: list = []
        self.returning: list = []
        self.bubble: Bubble | None = None
        self.said: dict[str, float] = {}
        self.surf = self.steal = self.hunt = None
        self.eaten = 0
        self.flee_dir, self.flip_t = 1, 0.0
        self.tune = tuning.current()
        self.t, self.cd, self.blackout_cd, self.count = 0.0, self.tune.terror_first_delay_s, 0.0, 0

    # ---- helpers
    def later(self, delay, fn):
        self.pending.append((self.t + delay, fn))

    def screen_geom(self):
        d = self.d
        scr = QGuiApplication.screenAt(QPoint(int(d.x), int(d.y - 50))) or QGuiApplication.primaryScreen()
        return scr.geometry()

    def say(self, cat):
        lines = LINES.get(cat)
        if not lines or self.t - self.said.get(cat, -99.0) < 3.0:
            return
        self.said[cat] = self.t
        if self.bubble is not None:
            self.bubble.kill()
        self.bubble = Bubble(random.choice(lines))
        self.place_bubble()

    def say_text(self, text):
        """Say something that isn't a canned line (his comments on your videos). Longer lines stay up longer."""
        if self.bubble is not None:
            self.bubble.kill()
        self.bubble = Bubble(text)
        self.bubble.LIFE = max(Bubble.LIFE, 1.5 + 0.065 * len(text))
        self.place_bubble()

    def place_bubble(self):
        if self.bubble is not None:
            self.bubble.follow(self.d.x, self.d.y - 115)

    def on_hit(self, kind):
        self.say(kind)
        self.sfx.play("ugh")

    def visible_icons(self):
        wins = self.d.world.wins
        out = []
        for name, (l, t, r, b) in self.probe.icons:
            cx, cy = (l + r) / 2, (t + b) / 2
            if r - l < 8 or any(w.rect[0] <= cx < w.rect[2] and w.rect[1] <= cy < w.rect[3] for w in wins):
                continue
            out.append((name, (l, t, r, b)))
        return out

    def busy(self):
        big = any(isinstance(w, (Shatter, Quake, Blackout)) for w in self.fx)
        return bool(self.surf or self.steal or self.hunt or big or self.d.war.tank is not None)

    # ---- triggering
    def trigger(self, kind) -> bool:
        d = self.d
        if getattr(d, "paused", False) or getattr(d, "napping", False):
            return False
        fn = getattr(self, "_" + kind, None)
        if fn is None:
            return False
        if kind in ("graffiti", "steal", "surf", "hunt") and (
            d.state in ("tanking", "held", "climb") or self.surf or self.steal or self.hunt
        ):
            return False
        ok = bool(fn())
        if ok:
            self.count += 1
        return ok

    def trigger_random(self):
        kinds = [k for k, _ in TERROR_MENU]
        random.shuffle(kinds)
        for k in kinds:
            if self.trigger(k):
                return k
        return None

    def auto(self, dt):
        d = self.d
        if not self.enabled or self.cd > 0 or d.state not in ("idle", "wander") or self.busy():
            return
        tn = self.tune
        angry = d.rage >= tn.rage_angry
        every = tn.terror_every_angry_s if angry else tn.terror_every_calm_s
        if every <= 0 or random.random() >= dt / every:
            return
        kinds = ["graffiti", "popup", "taunt"]
        if self.visible_icons():
            kinds.append("steal")
        if d.on_ground and d.plat_hwnd:
            kinds.append("surf")
        if self.probe.fish:
            kinds.append("hunt")
        if angry:
            kinds += ["glass", "quake"]
        if d.rage >= tn.rage_blackout and self.blackout_cd <= 0:
            kinds.append("blackout")
        weights = [tn.terror_weights.get(k, 0.0) for k in kinds]
        if sum(weights) <= 0:
            return
        kind = random.choices(kinds, weights=weights)[0]
        if self.trigger(kind):
            self.cd = random.uniform(*(tn.terror_cooldown_angry_s if angry else tn.terror_cooldown_calm_s))

    # ---- the acts
    def _taunt(self):
        self.say("bored")
        return True

    def _glass(self):
        d = self.d
        ix, iy = d.x + d.f * 85, d.y - 95
        if d.state not in ("tanking", "held"):
            d.vx = 0.0
            d.set_state("punch", 0.38)
        self.later(0.17, lambda: self._shatter(ix, iy))
        return True

    def _shatter(self, ix, iy):
        w, h = 340, 240
        wd = self.d.world
        floor = wd.floor_at(ix)
        x = min(max(ix - w / 2, wd.left), wd.right - w)
        y = min(max(iy - h / 2, wd.top), floor - h - 4)
        self.fx.append(Shatter(x, y, w, h, ix - x, iy - y, floor))
        self.sfx.play("glass")
        self.later(0.6, lambda: self.say("glass"))

    def _quake(self):
        d = self.d
        if d.on_ground and d.state not in ("tanking", "held"):
            d.jump(-700)
        self.later(0.55, self._start_quake)
        return True

    def _start_quake(self):
        self.fx.append(Quake(self.screen_geom()))
        self.sfx.play("rumble")
        self.say("quake")

    def _blackout(self):
        if getattr(self.d, "life", None) is not None:
            self.d.life.ha.flicker()
        d = self.d
        if d.state not in ("tanking", "held"):
            d.vx, d.lunge_v, d.kick_target = 0.0, 0.0, None
            d.set_state("slash", 0.6)
        self.blackout_cd = self.tune.blackout_cooldown_s
        self.later(0.3, lambda: self.fx.append(Blast(d.x + d.f * 40, d.y - 8, 14, 0.3)))
        self.later(0.38, self._start_blackout)
        self.later(1.0, lambda: self.say("blackout"))
        return True

    def _start_blackout(self):
        d = self.d
        self.fx.append(Blackout(self.screen_geom(), d.w32.cursor_pos))
        self.sfx.play("power")
        d.w32.bring_to_top(int(d.winId()))

    def _graffiti(self):
        """He goes there and sprays it himself (vandal.py): on bare wallpaper if he can find some, else high up."""
        vandal = getattr(self.d, "vandal", None)
        return bool(vandal is not None and vandal.start_spray())

    def _popup(self):
        g = self.screen_geom()
        x = g.x() + g.width() / 2 + random.uniform(-300, 300)
        y = g.y() + g.height() / 2 + random.uniform(-200, 150)
        self.fx.append(ErrorPopup(x, y, random.choice(POPUPS)))
        self.sfx.play("ding")
        return True

    def _steal(self):
        icons = self.visible_icons()
        if not icons:
            self.probe.request("icons")
            return False
        _name, (l, t, r, b) = random.choice(icons)
        pm = grab(l, t, r - l, b - t)
        ring = grab(l - 3, t - 3, r - l + 6, b - t + 6).toImage()
        bg = ring.pixelColor(1, 1) if not ring.isNull() else QColor(0, 0, 0)
        home = ((l + r) / 2, (t + b) / 2)
        copy = IconCopy(pm)
        copy.place_at(*home)
        self.steal = {"copy": copy, "ph": Stolen(l, t, r - l, b - t, bg), "home": home,
                      "phase": "yank", "t": 0.0, "from": home}
        d = self.d
        d.vx = 0.0
        d.set_state("flee", 9.0)
        self.sfx.play("yoink")
        self.say("steal")
        return True

    def _surf(self):
        d = self.d
        h = d.plat_hwnd
        if not (h and d.on_ground):
            return False
        raw, vis = d.w32.window_rect(h), d.world.rect_of(h)
        if raw is None or vis is None or d.w32.is_zoomed(h):
            return False
        wd = d.world
        direction = 1 if wd.right - vis[2] >= vis[0] - wd.left else -1
        self.surf = {"h": h, "x0": raw[0], "y0": raw[1], "vis": vis, "dx0": d.x, "dir": direction,
                     "t": 0.0, "last": (raw[0], raw[1]), "held": False}
        d.f = direction
        d.set_state("surf", 4.5)
        self.sfx.play("yoink")
        self.say("surf")
        return True

    def _hunt(self):
        if not self.probe.fish:
            self.probe.request("fish")
            return False
        self.hunt = {"until": self.t + 11.0, "next": 0.0, "pending": None}
        self.d.set_state("hunt", 11.0)
        self.say("hunt")
        return True

    # ---- per-frame
    def think(self, dt, cur, btn) -> bool:
        """Runs the dude's terror states. True = handled, skip the normal AI."""
        d = self.d
        s = d.state
        if s == "spray":
            d.vx = 0.0
            if d.st > d.state_len:
                d.set_state("idle", 1.5)
        elif s == "surf":
            self.think_surf(dt, btn)
        elif s == "flee":
            self.think_flee(dt, cur)
        elif s == "hunt":
            self.think_hunt(dt)
        elif s == "eat":
            self.think_eat(dt)
        else:
            return False
        return True

    def think_flee(self, dt, cur):
        d = self.d
        self.flip_t -= dt
        if self.flip_t <= 0 and abs(cur[0] - d.x) < 260:
            self.flee_dir = -1 if cur[0] > d.x else 1
        if d.blocked:
            self.flee_dir, self.flip_t = -self.flee_dir, 0.8
            d.jump(-900)
        d.walk(self.flee_dir * 270)
        if d.on_ground and random.random() < 0.7 * dt:
            d.jump(-random.uniform(650, 900))
        if d.st > d.state_len or self.steal is None:
            d.set_state("idle", 1.0)

    def think_surf(self, dt, btn):
        d, s = self.d, self.surf
        if s is None:
            d.set_state("idle", 1.0)
            return
        if btn:  # you're holding a mouse button: hands off, freeze
            s["held"] = True
            d.vx = 0.0
            return
        raw = d.w32.window_rect(s["h"])
        if raw is None or (raw[0], raw[1]) != s["last"]:  # closed, or you moved it: it's yours
            self.surf = None
            d.on_ground, d.plat_hwnd = False, None
            d.set_state("idle", 1.0)
            return
        if s["held"] or d.st > d.state_len:
            self.end_surf(jump=True)
            return
        s["t"] += dt
        wd = d.world
        vl, vt, vr, _vb = s["vis"]
        nx = d.x + s["dir"] * 250 * dt
        off = nx - s["dx0"]
        half = (vr - vl) * 0.3
        if vl + off < wd.left - half or vr + off > wd.right + half:
            s["dir"] = -s["dir"]
            d.f = s["dir"]
            nx = d.x
            off = nx - s["dx0"]
        dy = -abs(math.sin(s["t"] * 5)) * 22
        pos = (round(s["x0"] + off), round(s["y0"] + dy))
        d.w32.move_window(s["h"], *pos)
        s["last"] = pos
        d.x, d.y, d.vx, d.vy, d.on_ground = nx, vt + dy, 0.0, 0.0, True

    def end_surf(self, jump):
        d, s = self.d, self.surf
        self.surf = None
        if s is None:
            return
        raw = d.w32.window_rect(s["h"])
        if raw is not None and (raw[0], raw[1]) == s["last"] and s["last"] != (s["x0"], s["y0"]):
            self.returning.append({"h": s["h"], "from": s["last"], "to": (s["x0"], s["y0"]), "t": 0.0, "last": s["last"]})
        if d.state == "surf":
            d.on_ground, d.plat_hwnd = False, None
            if jump:
                d.vy, d.vx = -600.0, -d.f * 120.0
            d.set_state("idle", 1.0)

    def think_eat(self, dt):
        d, h = self.d, self.hunt
        c = h.get("corpse") if h else None
        if c is None or c.done:
            d.set_state("idle", 1.0)
            return
        d.vx = 0.0
        c.held = True
        hx, hy = d.limb("hand_a")
        c.x, c.y, c.rot = hx + 12 * d.f, hy - 4, -25.0 * d.f
        h["bite_t"] -= dt
        if h["bite_t"] > 0:
            return
        if c.bites >= c.BITES:
            c.kill()
            self.eaten += 1
            if getattr(d, "life", None) is not None:
                d.life.fish_eaten()
            self.hunt = None
            self.say("burp")
            self.sfx.play("burp")
            d.set_state("taunt", 1.6)
            return
        c.bite()
        self.sfx.play("chomp")
        h["bite_t"] = 0.65

    def think_hunt(self, dt):
        d, h = self.d, self.hunt
        if h is None:
            d.set_state("idle", 1.0)
            return
        c = h.get("corpse")
        if c is not None and c.done:
            h["corpse"] = c = None
        if c is not None:
            dx = c.x - d.x
            d.f = 1 if dx >= 0 else -1
            if c.landed and abs(dx) < 40 and abs(c.y - d.y) < 60 and d.on_ground:
                d.vx = 0.0
                d.set_state("eat", 99.0)
                h["bite_t"] = 0.5
                self.say("eat")
                return
            if abs(dx) > 20:
                d.walk(math.copysign(300, dx))
            else:
                d.vx = 0.0
            if c.landed:
                d.navigate(c.x, c.y + 10, dt)
            return
        fish = [f for f in self.probe.fish if 18 <= f[2] <= 220]
        if not fish:
            d.vx = 0.0
            return
        fx, fy, fw, _h = min(fish, key=lambda f: math.hypot(f[0] - d.x, f[1] - (d.y - 70)))
        dx = fx - d.x
        d.f = 1 if dx >= 0 else -1
        if abs(dx) < 80 and abs(fy - (d.y - 70)) < 90:
            d.vx = 0.0
            if d.attack_cd <= 0:
                d.lunge_v, d.kick_target = 0.0, None
                d.set_state("slash", 0.6)
                h["pending"] = (fx, fy, fw)
            return
        if abs(dx) > 25:
            d.walk(math.copysign(300, dx))
        else:
            d.vx = 0.0
        d.navigate(fx, fy + 70, dt)

    def step(self, dt, cur, btn):
        self.t += dt
        self.cd -= dt
        self.blackout_cd -= dt
        if self.pending:
            due = [p for p in self.pending if p[0] <= self.t]
            self.pending = [p for p in self.pending if p[0] > self.t]
            for _, fn in due:
                fn()
        self.fx = [w for w in self.fx if w.step(dt)]
        self.graffiti = [g for g in self.graffiti if g.step(dt)]
        if self.bubble is not None:
            if self.bubble.step(dt):
                self.place_bubble()
            else:
                self.bubble = None
        if self.surf is not None and self.d.state != "surf":
            self.end_surf(jump=False)
        self.step_returning(dt, btn)
        self.step_steal(dt)
        self.step_hunt()
        self.auto(dt)

    def step_returning(self, dt, btn):
        d, keep = self.d, []
        for r in self.returning:
            raw = d.w32.window_rect(r["h"])
            if raw is None or (raw[0], raw[1]) != r["last"]:
                continue  # you moved it yourself: leave it
            if btn:
                keep.append(r)
                continue
            r["t"] += dt
            k = min(1.0, r["t"] / 0.35)
            x, y = _lerp(r["from"], r["to"], _ease(k))
            pos = (round(x), round(y))
            d.w32.move_window(r["h"], *pos)
            r["last"] = pos
            if k < 1.0:
                keep.append(r)
        self.returning = keep

    def step_steal(self, dt):
        s, d = self.steal, self.d
        if s is None:
            return
        s["t"] += dt
        hand = (d.x, d.y - 150)
        if s["phase"] == "yank":
            k = min(1.0, s["t"] / 0.45)
            pos = _lerp(s["from"], hand, _ease(k))
            if k >= 1.0:
                s["phase"] = "carry"
        elif s["phase"] == "carry":
            pos = hand
            if d.state != "flee":
                if d.state in ("ragdoll", "held", "tanking"):
                    self.say("drop")
                s["phase"], s["t"], s["from"] = "back", 0.0, pos
        else:
            k = min(1.0, s["t"] / 0.5)
            pos = _lerp(s["from"], s["home"], _ease(k))
            if k >= 1.0:
                s["copy"].kill()
                s["ph"].kill()
                self.steal = None
                return
        s["copy"].place_at(*pos)

    def step_hunt(self):
        h, d = self.hunt, self.d
        if h is None:
            return
        if d.state in ("ragdoll", "held", "tanking") or self.t >= h["until"]:
            c = h.get("corpse")
            if c is not None and c.held:
                c.held, c.landed, c.vx, c.vy = False, False, 0.0, 0.0  # dropped his snack
            timeout = self.t >= h["until"]
            self.hunt = None
            if not timeout:
                return
            if d.state in ("hunt", "eat"):
                d.set_state("idle", 1.5)
            self.say("hunt_end")
            return
        if self.t >= h["next"]:
            self.probe.request("fish")
            h["next"] = self.t + 0.4
        if h["pending"] and d.state == "slash" and d.hit_done:
            x, y, w = h["pending"]
            self.fx.append(Splash(x, y))
            if h.get("corpse") is None:
                h["corpse"] = DeadFish(self, x, y, w)
                self.fx.append(h["corpse"])
                h["until"] = max(h["until"], self.t + 14.0)
                self.say("kill")
                self.sfx.play("splat")
            else:
                self.say("hunt_hit")
            h["pending"] = None
        if d.state in ("idle", "chase", "wander"):
            d.set_state("hunt", h["until"] - self.t)

    # ---- lifecycle
    def set_visible(self, vis):
        widgets = self.fx + self.graffiti + ([self.bubble] if self.bubble else [])
        if self.steal:
            widgets += [self.steal["copy"], self.steal["ph"]]
        for w in widgets:
            w.setVisible(vis)

    def release(self):
        """Undo everything temporary right now (pause, fullscreen nap, quit)."""
        d = self.d
        self.pending = []
        for w in self.fx:
            w.kill()
        self.fx = []
        if self.bubble is not None:
            self.bubble.kill()
            self.bubble = None
        backs = list(self.returning)
        self.returning = []
        s, self.surf = self.surf, None
        if s is not None:
            backs.append({"h": s["h"], "last": s["last"], "to": (s["x0"], s["y0"])})
        for r in backs:
            raw = d.w32.window_rect(r["h"])
            if raw is not None and (raw[0], raw[1]) == r["last"]:
                d.w32.move_window(r["h"], *r["to"])
        if self.steal is not None:
            self.steal["copy"].kill()
            self.steal["ph"].kill()
            self.steal = None
        self.hunt = None
        if d.state in STATES:
            if d.state == "surf":
                d.on_ground, d.plat_hwnd = False, None
            d.set_state("idle", 1.0)

    def clear_graffiti(self):
        for g in self.graffiti:
            g.kill()
        self.graffiti = []

    def close_all(self):
        self.release()
        self.clear_graffiti()
        self.probe.stop()
