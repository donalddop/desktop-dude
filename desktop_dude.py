"""Desktop Dude - a stick figure that lives on your desktop and fights your cursor.

Controls
  click him         punch him (knockback, he gets angrier)
  drag + release    throw him
  shake the mouse   break free when he grabs your cursor (or just click him)
  Ctrl+Alt+P        pause / resume
  Ctrl+Alt+Q        quit (panic button)

All damage is temporary: cursor shoves, window shakes snap back, cracks fade. Angry enough, he pulls a bazooka: dodge the rocket.
He carries a katana: dash-slashes, cuts windows, parries your clicks.
He climbs walls and windows, double jumps, and roams the whole screen.
Push him far enough and it's total war: drones, a tank, airstrikes (see warfare.py).
  Ctrl+Alt+W        enrage him right now (demo)
  Ctrl+Alt+M        drop a landmine under your cursor (wrecks tanks)
  Ctrl+Alt+F        place anti-air flak under your cursor (downs drones and bombers)
  Ctrl+Alt+T        desktop terror right now (see terror.py; graffiti sticks until you click it)
  Ctrl+Alt+D        duel: HP bars, best of 3 (again to stop)
  Ctrl+Alt+A        random weapon: bat, golf club, herring, chainsaw, shotgun, sniper, dynamite, pie...
He never clicks, types, closes/minimizes windows or touches files, and he
never moves the cursor while you hold a mouse button.
"""

from __future__ import annotations

import math
import os
import random
import sys
import time
import traceback
from collections import deque
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")  # 1 Qt px == 1 Win32 px

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QGuiApplication,
    QIcon,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

import tuning
from appdir import DATA, VERSION
from aquarium import Aquarium
from arsenal import WEAPONS, Arsenal
from life import Life
from terror import TERROR_MENU, Terror
from updater import Updater
from vandal import Vandal
from warfare import War

IS_WIN = sys.platform == "win32"
LOG = DATA / "desktop_dude.log"
G = 2400.0  # gravity, px/s^2


def log(msg: str) -> None:
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass


# --------------------------------------------------------------------------- world data


@dataclass
class WinInfo:
    hwnd: int
    rect: tuple[int, int, int, int]  # visible bounds l, t, r, b
    raw: tuple[int, int, int, int]  # GetWindowRect (what SetWindowPos uses)
    zoomed: bool


@dataclass
class Platform:
    x1: float
    x2: float
    y: float
    hwnd: int


def subtract_span(spans, lo, hi):
    out = []
    for a, b in spans:
        if hi <= a or lo >= b:
            out.append((a, b))
            continue
        if lo > a:
            out.append((a, lo))
        if hi < b:
            out.append((hi, b))
    return out


def compute_platforms(wins: list[WinInfo], top_limit: float = 40, min_width: float = 40):
    """Visible top edges of windows. `wins` is ordered top -> bottom (z-order)."""
    plats = []
    for i, w in enumerate(wins):
        l, t, r, b = w.rect
        if w.zoomed or r - l < 120 or b - t < 60 or t < top_limit:
            continue
        spans = [(l, r)]
        for o in wins[:i]:
            ol, ot, orr, ob = o.rect
            if ot < t and ob > t - 30:  # a window above covers the edge or his headroom
                spans = subtract_span(spans, ol, orr)
        plats += [Platform(a, b_, t, w.hwnd) for a, b_ in spans if b_ - a >= min_width]
    return plats


# --------------------------------------------------------------------------- Win32 layer


class Win32:
    """Thin ctypes wrapper. Only reads windows and moves the cursor/windows."""

    SKIP_CLASSES = frozenset({"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"})

    def __init__(self):
        import ctypes
        from ctypes import wintypes as wt

        self.ct, self.wt = ctypes, wt
        u = self.u = ctypes.WinDLL("user32", use_last_error=True)
        self.dwm = ctypes.WinDLL("dwmapi")

        class RECT(ctypes.Structure):
            _fields_ = [(n, ctypes.c_long) for n in ("l", "t", "r", "b")]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wt.DWORD),
                ("rcMonitor", RECT),
                ("rcWork", RECT),
                ("dwFlags", wt.DWORD),
            ]

        self.RECT, self.MONITORINFO = RECT, MONITORINFO
        self.WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        H = wt.HWND
        u.GetForegroundWindow.restype = H
        u.EnumWindows.argtypes = [self.WNDENUMPROC, wt.LPARAM]
        for fn in ("IsWindowVisible", "IsIconic", "IsZoomed", "GetWindowTextLengthW"):
            getattr(u, fn).argtypes = [H]
        u.GetWindowLongW.argtypes = [H, ctypes.c_int]
        u.GetWindowLongW.restype = ctypes.c_long
        u.SetWindowLongW.argtypes = [H, ctypes.c_int, ctypes.c_long]
        u.SetWindowLongW.restype = ctypes.c_long
        u.GetWindowRect.argtypes = [H, ctypes.POINTER(RECT)]
        u.SetWindowPos.argtypes = [H, H] + [ctypes.c_int] * 4 + [wt.UINT]
        u.GetClassNameW.argtypes = [H, wt.LPWSTR, ctypes.c_int]
        u.GetWindowThreadProcessId.argtypes = [H, ctypes.POINTER(wt.DWORD)]
        u.MonitorFromWindow.argtypes = [H, wt.DWORD]
        u.MonitorFromWindow.restype = wt.HMONITOR
        u.GetMonitorInfoW.argtypes = [wt.HMONITOR, ctypes.POINTER(MONITORINFO)]
        u.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
        u.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        u.GetAsyncKeyState.argtypes = [ctypes.c_int]
        u.GetAsyncKeyState.restype = ctypes.c_short
        self.dwm.DwmGetWindowAttribute.argtypes = [H, wt.DWORD, ctypes.c_void_p, wt.DWORD]
        self.pid = os.getpid()

    # input
    def cursor_pos(self):
        p = self.wt.POINT()
        self.u.GetCursorPos(self.ct.byref(p))
        return (p.x, p.y)

    def set_cursor(self, x, y):
        self.u.SetCursorPos(int(x), int(y))

    def _down(self, vk):
        return bool(self.u.GetAsyncKeyState(vk) & 0x8000)

    def buttons_down(self):
        return self._down(0x01) or self._down(0x02) or self._down(0x04)

    def hotkeys(self):
        if not (self._down(0x11) and self._down(0x12)):  # Ctrl + Alt
            return set()
        return {k for k, vk in (("q", 0x51), ("p", 0x50), ("w", 0x57), ("m", 0x4D), ("f", 0x46), ("t", 0x54), ("a", 0x41), ("d", 0x44)) if self._down(vk)}

    def foreground_title(self):
        u, wt = self.u, self.wt
        u.GetForegroundWindow.restype = wt.HWND
        u.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, self.ct.c_int]
        buf = self.ct.create_unicode_buffer(256)
        u.GetWindowTextW(u.GetForegroundWindow(), buf, 256)
        return buf.value

    def taskbar_parts(self):
        """Screen rects of the Start button and the clock (plain Win32, no clicking)."""
        u, wt = self.u, self.wt
        u.FindWindowW.restype = wt.HWND
        u.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
        u.FindWindowExW.restype = wt.HWND
        u.FindWindowExW.argtypes = [wt.HWND, wt.HWND, wt.LPCWSTR, wt.LPCWSTR]
        out = {}
        tb = u.FindWindowW("Shell_TrayWnd", None)
        if not tb:
            return out

        def rect(h):
            r = self.RECT()
            u.GetWindowRect(h, self.ct.byref(r))
            return (r.l, r.t, r.r, r.b)

        st = u.FindWindowExW(tb, None, "Start", None)
        if st:
            out["start"] = rect(st)
        tn = u.FindWindowExW(tb, None, "TrayNotifyWnd", None)
        ck = u.FindWindowExW(tn, None, "TrayClockWClass", None) if tn else None
        if ck:
            out["clock"] = rect(ck)
        return out

    # windows
    def _cls(self, h):
        buf = self.ct.create_unicode_buffer(256)
        self.u.GetClassNameW(h, buf, 256)
        return buf.value

    def _own(self, h):
        p = self.wt.DWORD()
        self.u.GetWindowThreadProcessId(h, self.ct.byref(p))
        return p.value == self.pid

    def windows(self):
        out = []
        ct, u = self.ct, self.u

        def cb(h, _):
            try:
                if not h or not u.IsWindowVisible(h) or u.IsIconic(h):
                    return True
                if u.GetWindowTextLengthW(h) == 0:
                    return True
                if u.GetWindowLongW(h, -20) & 0x80:  # WS_EX_TOOLWINDOW
                    return True
                cloaked = self.wt.DWORD(0)
                self.dwm.DwmGetWindowAttribute(h, 14, ct.byref(cloaked), 4)
                if cloaked.value or self._own(h) or self._cls(h) in self.SKIP_CLASSES:
                    return True
                raw = self.RECT()
                u.GetWindowRect(h, ct.byref(raw))
                vis = self.RECT()
                if self.dwm.DwmGetWindowAttribute(h, 9, ct.byref(vis), ct.sizeof(vis)) != 0:
                    vis = raw
                out.append(
                    WinInfo(
                        int(h),
                        (vis.l, vis.t, vis.r, vis.b),
                        (raw.l, raw.t, raw.r, raw.b),
                        bool(u.IsZoomed(h)),
                    )
                )
            except Exception:  # noqa: BLE001, S110 - never let a weird window kill the enumeration
                pass
            return True

        u.EnumWindows(self.WNDENUMPROC(cb), 0)
        return out

    def window_rect(self, h):
        r = self.RECT()
        if not self.u.GetWindowRect(h, self.ct.byref(r)):
            return None
        return (r.l, r.t, r.r, r.b)

    def move_window(self, h, x, y):
        # SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOOWNERZORDER
        self.u.SetWindowPos(h, None, int(x), int(y), 0, 0, 0x1 | 0x4 | 0x10 | 0x200)

    def is_zoomed(self, h):
        return bool(self.u.IsZoomed(h))

    def bring_to_top(self, h):
        # HWND_TOPMOST, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
        self.u.SetWindowPos(h, self.ct.c_void_p(-1), 0, 0, 0, 0, 0x1 | 0x2 | 0x10)

    def is_layered(self, h):
        return bool(self.u.GetWindowLongW(h, -20) & 0x80000)

    def set_click_through(self, h, on):
        ex = self.u.GetWindowLongW(h, -20)
        if not ex & 0x80000:  # only safe on layered windows
            return False
        new = ex | 0x20 if on else ex & ~0x20
        if new != ex:
            self.u.SetWindowLongW(h, -20, new)
        return True

    def foreground_fullscreen(self):
        h = self.u.GetForegroundWindow()
        if not h or self._own(h) or self._cls(h) in self.SKIP_CLASSES:
            return False
        r = self.RECT()
        self.u.GetWindowRect(h, self.ct.byref(r))
        mi = self.MONITORINFO()
        mi.cbSize = self.ct.sizeof(mi)
        if not self.u.GetMonitorInfoW(self.u.MonitorFromWindow(h, 2), self.ct.byref(mi)):
            return False
        m = mi.rcMonitor
        return r.l <= m.l and r.t <= m.t and r.r >= m.r and r.b >= m.b


    # the wallpaper layer: the WorkerW window behind the desktop icons (the Wallpaper Engine trick)
    def _workerw(self):
        ct, wt, u = self.ct, self.wt, self.u
        ww = getattr(self, "_ww", None)
        if ww and u.IsWindow(ww):
            return ww
        self._ww = None
        try:
            H = wt.HWND
            u.IsWindow.argtypes = [H]
            u.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
            u.FindWindowW.restype = H
            u.FindWindowExW.argtypes = [H, H, wt.LPCWSTR, wt.LPCWSTR]
            u.FindWindowExW.restype = H
            u.SendMessageTimeoutW.argtypes = [H, wt.UINT, wt.WPARAM, wt.LPARAM, wt.UINT, wt.UINT,
                                              ct.POINTER(ct.c_size_t)]
            progman = u.FindWindowW("Progman", None)
            if not progman:
                return None
            res = ct.c_size_t()
            u.SendMessageTimeoutW(progman, 0x052C, 0xD, 0x1, 0, 1000, ct.byref(res))
            found = []

            def cb(h, _):
                if u.FindWindowExW(h, None, "SHELLDLL_DefView", None):
                    w = u.FindWindowExW(None, h, "WorkerW", None)
                    if w:
                        found.append(w)
                return True

            u.EnumWindows(self.WNDENUMPROC(cb), 0)
            # Windows 11 24H2 keeps the WorkerW inside Progman instead
            self._ww = found[0] if found else u.FindWindowExW(progman, None, "WorkerW", None)
        except Exception:  # noqa: BLE001 - no wallpaper layer: he just won't vandalise it
            self._ww = None
        return self._ww or None

    def wall_origin(self):
        ww = self._workerw()
        if not ww:
            return None
        pt = self.wt.POINT(0, 0)
        self.u.ClientToScreen.argtypes = [self.wt.HWND, self.ct.POINTER(self.wt.POINT)]
        self.u.ClientToScreen(ww, self.ct.byref(pt))
        return pt.x, pt.y

    def wall_adopt(self, hwnd):
        ww = self._workerw()
        if not ww:
            return False
        self.u.SetParent.argtypes = [self.wt.HWND, self.wt.HWND]
        self.u.SetParent.restype = self.wt.HWND
        return bool(self.u.SetParent(hwnd, ww))

    def wallpaper_grab(self, x, y, w, h):
        """What your wallpaper looks like at x, y, w, h (without icons): PrintWindow of the wallpaper layer."""
        ww = self._workerw()
        if not ww:
            return None
        try:
            from PySide6.QtGui import QImage

            ct, wt, u = self.ct, self.wt, self.u
            g = ct.WinDLL("gdi32")
            vp = ct.c_void_p
            for fn, res, args in (("CreateCompatibleDC", vp, [vp]), ("CreateCompatibleBitmap", vp, [vp, ct.c_int, ct.c_int]),
                                  ("SelectObject", vp, [vp, vp]), ("DeleteObject", ct.c_int, [vp]),
                                  ("DeleteDC", ct.c_int, [vp])):
                getattr(g, fn).restype, getattr(g, fn).argtypes = res, args
            u.GetDC.restype, u.GetDC.argtypes = vp, [wt.HWND]
            u.ReleaseDC.argtypes = [wt.HWND, vp]
            u.PrintWindow.argtypes = [wt.HWND, vp, wt.UINT]
            r = self.RECT()
            u.GetWindowRect(ww, ct.byref(r))
            sdc = u.GetDC(None)
            mdc = g.CreateCompatibleDC(sdc)
            bmp = g.CreateCompatibleBitmap(sdc, r.r - r.l, r.b - r.t)
            old = g.SelectObject(mdc, bmp)
            u.PrintWindow(ww, mdc, 2)
            g.SelectObject(mdc, old)
            img = QImage.fromHBITMAP(bmp)
            g.DeleteObject(bmp)
            g.DeleteDC(mdc)
            u.ReleaseDC(None, sdc)
            return img.copy(int(x - r.l), int(y - r.t), int(w), int(h))
        except Exception:  # noqa: BLE001
            return None


class FakeWin32:
    """Stand-in for tests / non-Windows runs."""

    def __init__(self):
        self.cursor = (400, 300)
        self.keys: set[str] = set()
        self.buttons = False
        self.wins = [
            WinInfo(101, (60, 300, 420, 560), (60, 300, 420, 560), False),
            WinInfo(102, (350, 220, 700, 450), (350, 220, 700, 450), False),
        ]
        self.orig = {w.hwnd: w.raw[:2] for w in self.wins}
        self.pos = dict(self.orig)
        self.moves = 0
        self.title = ""
        self.parts: dict = {}

    def cursor_pos(self):
        return self.cursor

    def set_cursor(self, x, y):
        self.cursor = (int(x), int(y))

    def buttons_down(self):
        return self.buttons

    def hotkeys(self):
        return self.keys

    def windows(self):
        return list(self.wins)

    def window_rect(self, h):
        p = self.pos.get(h)
        return (*p, p[0] + 100, p[1] + 100) if p else None

    def move_window(self, h, x, y):
        self.pos[h] = (int(x), int(y))
        self.moves += 1

    def is_zoomed(self, h):
        return False

    def bring_to_top(self, h):
        pass

    def is_layered(self, h):
        return False

    def set_click_through(self, h, on):
        return False

    def foreground_fullscreen(self):
        return False

    def foreground_title(self):
        return self.title

    def wall_origin(self):
        return (0, 0)

    def wall_adopt(self, hwnd):
        return True

    def wallpaper_grab(self, x, y, w, h):
        return None

    def taskbar_parts(self):
        return dict(self.parts)


# --------------------------------------------------------------------------- the body

THIGH, SHIN, TORSO, UPPER, LOWER, HEAD_R = 20.0, 20.0, 34.0, 15.0, 15.0, 10.0


@dataclass
class Pose:
    """Segment angles in radians: 0 = straight down, pi/2 = forward, pi = straight up.
    Tuples are (limb a, limb b)."""

    lean: float = 0.0
    thigh: tuple[float, float] = (0.12, -0.12)
    shin: tuple[float, float] = (0.06, -0.06)
    upper: tuple[float, float] = (0.25, -0.2)
    lower: tuple[float, float] = (0.05, -0.3)
    spin: float = 0.0


def _seg(p, ang, length, f):
    return (p[0] + math.sin(ang) * length * f, p[1] + math.cos(ang) * length)


def skeleton(p: Pose, f: int) -> dict[str, tuple[float, float]]:
    """Joint positions relative to the feet point (y grows downward)."""
    h = max(math.cos(p.thigh[i]) * THIGH + math.cos(p.shin[i]) * SHIN for i in (0, 1))
    hip = (0.0, -max(h, 12.0))
    pts = {"hip": hip}
    for i, n in enumerate("ab"):
        pts["knee_" + n] = k = _seg(hip, p.thigh[i], THIGH, f)
        pts["foot_" + n] = _seg(k, p.shin[i], SHIN, f)
    sl, cl = math.sin(p.lean) * f, math.cos(p.lean)
    neck = (hip[0] + sl * TORSO, hip[1] - cl * TORSO)
    pts["neck"] = neck
    pts["head"] = (neck[0] + sl * (HEAD_R + 2), neck[1] - cl * (HEAD_R + 2))
    sh = (hip[0] + (neck[0] - hip[0]) * 0.8, hip[1] + (neck[1] - hip[1]) * 0.8)
    pts["shoulder"] = sh
    for i, n in enumerate("ab"):
        pts["elbow_" + n] = e = _seg(sh, p.upper[i], UPPER, f)
        pts["hand_" + n] = _seg(e, p.lower[i], LOWER, f)
    if p.spin:
        c, s = math.cos(p.spin), math.sin(p.spin)
        hx, hy = hip
        pts = {
            k: (hx + (x - hx) * c - (y - hy) * s, hy + (x - hx) * s + (y - hy) * c)
            for k, (x, y) in pts.items()
        }
    return pts


def pose_eat(t):
    """Snack in hand at his mouth, chewing."""
    c = math.sin(t * 14) * 0.08
    return Pose(0.08 + c * 0.5, (0.12, -0.12), (0.06, -0.06), (1.9 + c, -0.2), (3.3 + c, -0.3))


def pose_stand(t):
    b = math.sin(t * 2.2) * 0.05
    return Pose(0.02, (0.12, -0.12), (0.06, -0.06), (0.25 + b, -0.2 - b), (0.05, -0.3))


def pose_walk(ph, amp=0.5, lean=0.08, arm_bend=0.5):
    s, c = math.sin(ph), math.cos(ph)
    ta, tb = amp * s, -amp * s
    sa = ta - (0.15 + 0.9 * amp * max(0.0, c))
    sb = tb - (0.15 + 0.9 * amp * max(0.0, -c))
    ua, ub = -0.9 * amp * s, 0.9 * amp * s
    return Pose(lean, (ta, tb), (sa, sb), (ua, ub), (ua + arm_bend, ub + arm_bend))


def pose_air(vy, t):
    if vy < 0:
        return Pose(0.1, (0.9, -0.2), (0.1, -0.8), (2.2, -2.3), (2.6, -2.7))
    w = math.sin(t * 14) * 0.35
    return Pose(0.0, (0.4, -0.3), (0.0, -0.5), (1.9 + w, -1.9 - w), (2.2 + w, -2.2 - w))


def pose_punch(k):
    legs = ((0.38, -0.32), (0.18, -0.42))
    if k < 0.45:  # wind up
        return Pose(-0.1, *legs, (-0.7, 0.5), (0.6, 2.0))
    return Pose(0.3, *legs, (1.55, 0.4), (1.57, 2.2))


def pose_kick(k):
    if k < 0.4:
        return Pose(-0.1, (0.9, -0.1), (-0.3, -0.1), (-0.6, 1.0), (-0.3, 1.5))
    return Pose(-0.3, (1.55, -0.15), (1.6, -0.15), (-1.0, 1.3), (-0.6, 1.8))


def pose_grab(ph):
    p = pose_walk(ph, 0.75, 0.15, 1.0)
    p.upper = (2.1, p.upper[1])
    p.lower = (2.3, p.lower[1])
    return p


def pose_taunt(t):
    w = math.sin(t * 18) * 0.3
    return Pose(-0.05, (0.2, -0.2), (0.1, -0.1), (2.2 + w, -2.2 + w), (2.7 + w, -2.7 + w))


def pose_ragdoll(t, spin):
    s = math.sin
    return Pose(
        0.0,
        (0.6 + 0.5 * s(t * 9), -0.5 + 0.5 * s(t * 7)),
        (0.2 + 0.4 * s(t * 11), -0.6 + 0.3 * s(t * 8)),
        (2.0 + 0.8 * s(t * 10), -1.8 + 0.8 * s(t * 12)),
        (2.4 + 0.6 * s(t * 13), -2.2 + 0.5 * s(t * 9)),
        spin,
    )


def pose_crouch():
    return Pose(0.35, (1.2, 0.9), (-0.5, -0.7), (0.8, 0.6), (1.2, 1.0))


def pose_dizzy(t):
    w = math.sin(t * 5) * 0.22
    return Pose(w, (0.15 + w, -0.15 + w), (0.05, -0.05), (0.4 - w, -0.4 - w), (0.2, -0.2))


def pose_aim(ang, recoil=0.0):
    return Pose(-0.1 - 0.2 * recoil, (0.4, -0.35), (0.2, -0.5), (ang, ang - 0.9), (ang, ang + 0.5))


def slash_blade(k):
    """Blade angle through a slash: raised behind him, swept forward and down."""
    if k < 0.35:
        return 3.6
    if k < 0.6:
        return 3.6 - 3.2 * (k - 0.35) / 0.25
    return 0.4


def pose_slash(k):
    b = slash_blade(k)
    lunge = 0.0 if k < 0.3 else 1.0
    return Pose(
        -0.1 if k < 0.35 else 0.35,
        (0.25 + 0.5 * lunge, -0.25 - 0.3 * lunge),
        (0.1 - 0.1 * lunge, -0.35 - 0.3 * lunge),
        (b - 0.5, b - 0.8),
        (b - 0.1, b - 0.2),
    )


def pose_climb(t):
    s = math.sin(t * 10)
    return Pose(0.25, (0.9 + 0.4 * s, 0.9 - 0.4 * s), (-0.2, -0.2), (2.6 + 0.4 * s, 2.6 - 0.4 * s), (2.9, 2.9))


def draw_katana(qp: QPainter, hx, hy, ang, f):
    ux, uy = math.sin(ang) * f, math.cos(ang)
    nx, ny = -uy * f, ux * f  # slight curve toward the blade's back
    path = QPainterPath(QPointF(hx + ux * 5, hy + uy * 5))
    path.quadTo(QPointF(hx + ux * 34 + nx * 4, hy + uy * 34 + ny * 4), QPointF(hx + ux * 62, hy + uy * 62))
    qp.setBrush(Qt.NoBrush)
    for w, col in ((5.0, QColor(255, 255, 255, 170)), (2.6, QColor(196, 202, 214))):
        qp.setPen(QPen(col, w, Qt.SolidLine, Qt.RoundCap))
        qp.drawPath(path)
    qp.setPen(QPen(QColor(25, 25, 25), 4, Qt.SolidLine, Qt.RoundCap))
    qp.drawLine(QPointF(hx - ux * 10, hy - uy * 10), QPointF(hx + ux * 3, hy + uy * 3))
    qp.setPen(Qt.NoPen)
    qp.setBrush(QColor(170, 140, 60))
    qp.drawEllipse(QPointF(hx + ux * 4, hy + uy * 4), 3.5, 3.5)
    qp.setBrush(Qt.NoBrush)


def pose_spray(t):
    w = math.sin(t * 9) * 0.12
    return Pose(0.05, (0.2, -0.15), (0.1, -0.1), (1.45 + w, -0.25), (1.6 + w, -0.4))


def pose_surf(t):
    w = math.sin(t * 7) * 0.25
    return Pose(0.15, (0.6, -0.5), (-0.3, -0.1), (1.9 + w, -1.9 - w), (2.4 + w, -2.4 - w))


def pose_carry(ph):
    p = pose_walk(ph, 0.85, 0.2, 1.3)
    p.upper, p.lower = (2.9, -2.9), (3.1, -3.1)
    return p


def pose_held(t):
    w = math.sin(t * 16) * 0.4
    return Pose(0.0, (0.3 + w, -0.3 - w), (w, -0.2 - w), (2.3, -2.3), (2.8, -2.8))


LINES = [
    ("hip", "neck"),
    ("hip", "knee_a"),
    ("knee_a", "foot_a"),
    ("hip", "knee_b"),
    ("knee_b", "foot_b"),
    ("shoulder", "elbow_a"),
    ("elbow_a", "hand_a"),
    ("shoulder", "elbow_b"),
    ("elbow_b", "hand_b"),
]


def draw_dude(qp: QPainter, ox, oy, pose: Pose, f: int, color: QColor, scale=1.0):
    pts = skeleton(pose, f)

    def P(k):
        return QPointF(ox + pts[k][0] * scale, oy + pts[k][1] * scale)

    for width, col, grow in ((7.5, QColor(255, 255, 255, 190), 1.8), (4.2, color, 0.0)):
        qp.setPen(QPen(col, width * scale, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for a, b in LINES:
            qp.drawLine(P(a), P(b))
        qp.setBrush(col)
        r = (HEAD_R + grow) * scale
        qp.drawEllipse(P("head"), r, r)
    # eye, looking where he faces
    a = pose.spin
    ex, ey = 4.0 * f, -2.0
    ex, ey = ex * math.cos(a) - ey * math.sin(a), ex * math.sin(a) + ey * math.cos(a)
    qp.setPen(Qt.NoPen)
    qp.setBrush(QColor(255, 255, 255))
    h = P("head")
    qp.drawEllipse(QPointF(h.x() + ex * scale, h.y() + ey * scale), 2.2 * scale, 2.2 * scale)
    qp.setBrush(Qt.NoBrush)


# --------------------------------------------------------------------------- effects


class Crack(QWidget):
    """Temporary damage mark. Click-through, fades out."""

    SIZE, LIFE, FADE = 130, 10.0, 3.0

    def __init__(self, x, y):
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
            | Qt.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.move(int(x - self.SIZE / 2), int(y - self.SIZE / 2))
        self.age = 0.0
        c = self.SIZE / 2
        n = random.randint(5, 8)
        self.rays = []
        for i in range(n):
            ang = i / n * math.tau + random.uniform(-0.3, 0.3)
            px, py = c, c
            pts = [QPointF(px, py)]
            for _ in range(random.randint(3, 5)):
                ang += random.uniform(-0.5, 0.5)
                step = random.uniform(7, 12)
                px, py = px + math.cos(ang) * step, py + math.sin(ang) * step
                pts.append(QPointF(px, py))
            self.rays.append(QPolygonF(pts))
        self.show()

    def step(self, dt) -> bool:
        self.age += dt
        if self.age >= self.LIFE:
            self.close()
            self.deleteLater()
            return False
        if self.age > self.LIFE - self.FADE:
            self.setWindowOpacity(max(0.0, (self.LIFE - self.age) / self.FADE))
        return True

    def paintEvent(self, _):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        for w, col in ((4.0, QColor(255, 255, 255, 150)), (1.8, QColor(20, 20, 20, 230))):
            qp.setPen(QPen(col, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            for poly in self.rays:
                qp.drawPolyline(poly)


FX_FLAGS = (
    Qt.FramelessWindowHint
    | Qt.WindowStaysOnTopHint
    | Qt.Tool
    | Qt.WindowDoesNotAcceptFocus
    | Qt.WindowTransparentForInput
)


class _Overlay(QWidget):
    """Small click-through, always-on-top effect window."""

    def __init__(self, size):
        super().__init__(None, FX_FLAGS)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(size, size)
        self.size_ = size

    def center_on(self, x, y):
        self.move(round(x - self.size_ / 2), round(y - self.size_ / 2))


class Rocket(_Overlay):
    """Flies straight; explodes at its target range, on the floor/edges, or on a direct cursor hit."""

    def __init__(self, x, y, ux, uy, speed, reach):
        super().__init__(48)
        self.x, self.y, self.ux, self.uy = x, y, ux, uy
        self.speed, self.reach, self.travel = speed, reach, 0.0
        self.angle = math.degrees(math.atan2(uy, ux))
        self.center_on(x, y)
        self.show()

    def step(self, dt, cur, world):
        s = self.speed * dt
        self.x += self.ux * s
        self.y += self.uy * s
        self.travel += s
        floor = world.floor_at(self.x)
        gone = not (world.left <= self.x <= world.right and world.top <= self.y < floor)
        if gone or self.travel >= self.reach or math.hypot(cur[0] - self.x, cur[1] - self.y) < 26:
            self.close()
            self.deleteLater()
            return world.clamp(self.x, min(self.y, floor - 4))
        self.center_on(self.x, self.y)
        self.update()
        return None

    def paintEvent(self, _):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        qp.translate(self.size_ / 2, self.size_ / 2)
        qp.rotate(self.angle)
        k = random.uniform(0.7, 1.25)
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(255, 140, 30, 220))
        qp.drawEllipse(QPointF(-16, 0), 9 * k, 4.5 * k)
        qp.setBrush(QColor(255, 240, 140))
        qp.drawEllipse(QPointF(-13, 0), 4 * k, 2.2 * k)
        qp.setBrush(QColor(35, 40, 25))
        for sg in (-1, 1):
            qp.drawPolygon(QPolygonF([QPointF(-10, 3.5 * sg), QPointF(-14, 8 * sg), QPointF(-5, 3.5 * sg)]))
        qp.setPen(QPen(QColor(255, 255, 255, 190), 1.5))
        qp.setBrush(QColor(70, 90, 45))
        qp.drawRoundedRect(QRectF(-10, -3.5, 18, 7), 2, 2)
        qp.setBrush(QColor(200, 40, 30))
        qp.drawPolygon(QPolygonF([QPointF(8, -3.5), QPointF(15, 0), QPointF(8, 3.5)]))


class Slash(_Overlay):
    """Katana cut: a thin dark gash with a gleam. Fades out."""

    LIFE, FADE, HALF = 6.0, 2.0, 120

    def __init__(self, x, y, ang):
        super().__init__(2 * self.HALF + 20)
        self.age, self.ang = 0.0, math.degrees(ang)
        self.center_on(x, y)
        self.show()

    def step(self, dt) -> bool:
        self.age += dt
        if self.age >= self.LIFE:
            self.close()
            self.deleteLater()
            return False
        if self.age < 0.35:
            self.update()
        elif self.age > self.LIFE - self.FADE:
            self.setWindowOpacity(max(0.0, (self.LIFE - self.age) / self.FADE))
        return True

    def paintEvent(self, _):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        qp.translate(self.size_ / 2, self.size_ / 2)
        qp.rotate(self.ang)
        half = self.HALF * min(1.0, self.age / 0.08)
        qp.setPen(QPen(QColor(255, 255, 255, 160), 1.2))
        qp.setBrush(QColor(15, 15, 18, 235))
        qp.drawPolygon(QPolygonF([QPointF(-half, 0), QPointF(0, -2.8), QPointF(half, 0), QPointF(0, 2.8)]))
        if self.age < 0.35:
            a = int(230 * (1 - self.age / 0.35))
            qp.setPen(QPen(QColor(255, 255, 255, a), 5, Qt.SolidLine, Qt.RoundCap))
            qp.drawLine(QPointF(-half, -1), QPointF(half, -1))


class Boom(_Overlay):
    LIFE = 0.55

    def __init__(self, x, y):
        super().__init__(300)
        self.age = 0.0
        self.debris = [(random.uniform(0, math.tau), random.uniform(60, 130)) for _ in range(12)]
        self.center_on(x, y)
        self.show()

    def step(self, dt) -> bool:
        self.age += dt
        if self.age >= self.LIFE:
            self.close()
            self.deleteLater()
            return False
        self.update()
        return True

    def paintEvent(self, _):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        k = self.age / self.LIFE
        fade = 1 - k
        c = QPointF(self.size_ / 2, self.size_ / 2)
        r = 18 + 110 * (1 - (1 - k) ** 2)
        qp.setPen(QPen(QColor(90, 90, 90, int(120 * fade)), 5))
        qp.setBrush(QColor(255, 110, 20, int(230 * fade)))
        qp.drawEllipse(c, r, r)
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(255, 220, 80, int(255 * fade**1.5)))
        qp.drawEllipse(c, r * 0.62, r * 0.62)
        if k < 0.3:
            qp.setBrush(QColor(255, 255, 240, int(255 * (1 - k / 0.3))))
            qp.drawEllipse(c, r * 0.3, r * 0.3)
        qp.setPen(QPen(QColor(50, 40, 30, int(230 * fade)), 3, Qt.SolidLine, Qt.RoundCap))
        for ang, sp in self.debris:
            d0, d1 = r * 0.7, r * 0.7 + 10 + sp * k * 0.4
            qp.drawLine(
                QPointF(c.x() + math.cos(ang) * d0, c.y() + math.sin(ang) * d0),
                QPointF(c.x() + math.cos(ang) * d1, c.y() + math.sin(ang) * d1),
            )


class Shaker:
    """Shakes a window for a moment, then puts it back exactly where it was."""

    DUR = 0.45
    SLICE_DUR = 0.7

    def __init__(self, w32):
        self.w32 = w32
        self.active: dict[int, list] = {}

    def slice(self, hwnd, direction) -> bool:
        """Window slides along the cut, then snaps back."""
        return self.shake(hwnd, 1 if direction >= 0 else -1)

    def shake(self, hwnd, slice_dir=0) -> bool:
        if hwnd in self.active or self.w32.is_zoomed(hwnd):
            return False
        r = self.w32.window_rect(hwnd)
        if r is None:
            return False
        self.active[hwnd] = [r[0], r[1], 0.0, slice_dir]
        return True

    def step(self, dt):
        for hwnd, s in list(self.active.items()):
            s[2] += dt
            t, sd = s[2], s[3]
            dur = self.SLICE_DUR if sd else self.DUR
            if t >= dur:
                self.w32.move_window(hwnd, s[0], s[1])
                del self.active[hwnd]
                continue
            k = 1 - t / dur
            if sd:
                self.w32.move_window(hwnd, s[0] + sd * 22 * k * k, s[1] + 14 * k * k)
                continue
            self.w32.move_window(
                hwnd, s[0] + 16 * k * math.sin(t * 60), s[1] + 5 * k * math.cos(t * 47)
            )

    def restore_all(self):
        for hwnd, s in self.active.items():
            self.w32.move_window(hwnd, s[0], s[1])
        self.active.clear()


# --------------------------------------------------------------------------- world


class World:
    def __init__(self, w32):
        self.w32 = w32
        self.wins: list[WinInfo] = []
        self.plats: list[Platform] = []
        self.refresh_screens()

    def refresh_screens(self):
        self.screens = []
        for s in QGuiApplication.screens():
            g, a = s.geometry(), s.availableGeometry()
            self.screens.append((g.x(), g.y(), g.x() + g.width(), g.y() + g.height(), a.y() + a.height()))
        v = QGuiApplication.primaryScreen().virtualGeometry()
        self.left, self.top = v.x(), v.y()
        self.right, self.bottom = v.x() + v.width(), v.y() + v.height()
        p = QGuiApplication.primaryScreen().geometry()
        self.spawn = (p.x() + p.width() / 2, p.y() + 150)

    def refresh(self):
        self.wins = self.w32.windows()
        self.plats = compute_platforms(self.wins, self.top + 40)

    def screen_at(self, x):
        for s in self.screens:
            if s[0] <= x < s[2]:
                return s
        return min(self.screens, key=lambda s: min(abs(x - s[0]), abs(x - s[2])))

    def floor_at(self, x):
        return self.screen_at(x)[4]

    def plat(self, hwnd, x):
        for p in self.plats:
            if p.hwnd == hwnd and p.x1 - 4 <= x <= p.x2 + 4:
                return p
        return None

    def window_at(self, x, y):
        for w in self.wins:  # top -> bottom, first hit is what you see
            l, t, r, b = w.rect
            if l <= x < r and t <= y < b:
                return None if w.zoomed else w
        return None

    def wall_ahead(self, x, y, f, reach=16):
        """Nearest climbable wall in front of him within `reach`:
        (wall x, top or None for a screen edge, hwnd)."""
        cands = []
        edge = self.right - 12 if f > 0 else self.left + 12
        if 0 <= (edge - x) * f < reach + 12:
            cands.append((abs(edge - x), edge, None, None))
        for w in self.wins:
            if w.zoomed:
                continue
            l, t, r, b = w.rect
            side = l if f > 0 else r
            if (
                0 <= (side - x) * f < reach
                and t + 30 < y <= b + 160
                and t >= self.top + 40
                and any(p.hwnd == w.hwnd and p.x1 - 2 <= side + f * 25 <= p.x2 + 2 for p in self.plats)
            ):
                cands.append((abs(side - x), side, t, w.hwnd))
        if not cands:
            return None
        _, side, top, hwnd = min(cands, key=lambda c: c[0])
        return side, top, hwnd

    def rect_of(self, hwnd):
        for w in self.wins:
            if w.hwnd == hwnd:
                return w.rect
        return None

    def clamp(self, x, y):
        return (min(max(x, self.left + 2), self.right - 3), min(max(y, self.top + 2), self.bottom - 3))


# --------------------------------------------------------------------------- the dude

W, H = 240, 210
FX, FY = 120, 165  # feet point inside his window
IDLE, WANDER, NOTICE, CHASE, PUNCH, GRAB, KICK, TAUNT, RAGDOLL, GETUP, HELD, STUNNED = (
    ["idle", "wander", "notice", "chase", "punch", "grab", "kick", "taunt", "ragdoll", "getup", "held", "stunned"]
)
CALM, ANGRY = (28, 28, 34), (205, 35, 35)
AIM, RECOIL = "aim", "recoil"
SLASH, CLIMB = "slash", "climb"
TANKING = "tanking"


class Dude(QWidget):
    def __init__(self, w32, clock=time.perf_counter):
        super().__init__(
            None,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(W, H)
        self.w32, self.clock = w32, clock
        self.world = World(w32)
        self.world.refresh()
        self.shaker = Shaker(w32)
        self.cracks: list[Crack] = []
        self.rockets: list[Rocket] = []
        self.booms: list[Boom] = []
        self.tune = tuning.current()
        self.war = War(self)
        self.terror = Terror(self, real=isinstance(w32, Win32))
        self.arsenal = Arsenal(self, Pose, Slash)
        self.updater = Updater(real=isinstance(w32, Win32))
        self.aqua = None
        self.update_url = None
        self.life = Life(self, {"Pose": Pose, "draw": draw_dude, "skeleton": skeleton, "pose_kick": pose_kick, "pose_crouch": pose_crouch, "pose_walk": pose_walk, "pose_stand": pose_stand, "pose_punch": pose_punch, "pose_eat": pose_eat, "pose_air": pose_air, "pose_spray": pose_spray}, real=isinstance(w32, Win32))
        self.aqua = Aquarium(self, self.life.kit, real=isinstance(w32, Win32))
        self.vandal = Vandal(self, self.life.kit, real=isinstance(w32, Win32))
        self.fx: list[tuple] = []
        self.errors = 0
        self.tray = None
        self.respawn()
        self.rage = 0.0
        self.paused = self.napping = False
        self.keys_prev: dict[str, bool] = {}
        self.clickable = None
        self.press = None
        self.drag_off = (0.0, 0.0)
        self.samples: deque = deque(maxlen=10)
        self.t = self.phase = 0.0
        self.dt = 1 / 60
        self.next_world = self.next_fs = self.next_screens = 0.0
        self.last = clock()
        self.pose = pose_stand(0)
        self.place()
        self.show()
        log(f"started; layered window={w32.is_layered(int(self.winId()))}")
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

    # ---- helpers
    def respawn(self):
        war = getattr(self, "war", None)
        if war is not None and hasattr(self, "paused"):
            war.clear()
            self.terror.release()
            if getattr(self, "arsenal", None) is not None:
                self.arsenal.release()
            if getattr(self, "life", None) is not None:
                self.life.release()
            if getattr(self, "aqua", None) is not None:
                self.aqua.release()
            if getattr(self, "vandal", None) is not None:
                self.vandal.release()
            self.sync_visible()
        self.x, self.y = self.world.spawn
        self.vx = self.vy = 0.0
        self.f = 1
        self.on_ground, self.plat_hwnd, self.drop_until = False, None, 0.0
        self.spin = self.spin_v = 0.0
        self.shove = None
        self.grab_last, self.struggle, self.grab_dir = None, 0.0, 1
        self.kick_target, self.blocked = None, False
        self.attack_cd = 1.5
        self.bazooka_cd, self.aim = 4.0, 1.6
        self.katana_cd, self.lunge_v = 2.0, 0.0
        self.double_jumped, self.climb_cd = False, 0.0
        self.climb_x = self.climb_top = 0.0
        self.climb_hwnd, self.climb_return, self.climb_return_len = None, IDLE, 1.0
        self.target_x, self.target_y, self.wander_speed = self.x, self.y, 130.0
        self.set_state(IDLE, 1.0)

    def set_state(self, s, length=1.0):
        self.state, self.st, self.state_len, self.hit_done = s, 0.0, length, False

    def limb(self, name, pose=None):
        px, py = skeleton(pose or self.pose, self.f)[name]
        return self.x + px, self.y + py

    def walk(self, v):
        self.vx = v
        self.f = 1 if v > 0 else -1

    def jump(self, v):
        if self.on_ground:
            self.vy, self.on_ground, self.plat_hwnd = v, False, None

    def drop(self):
        self.drop_until = self.clock() + 0.3
        self.on_ground, self.plat_hwnd, self.vy = False, None, 60.0

    def add_fx(self, x, y, kind):
        self.fx.append((x, y, 0.0, kind))

    def spawn_crack(self, x, y):
        self.add_mark(Crack(x, y))

    def add_mark(self, mark):
        while len(self.cracks) >= 24:
            self.cracks.pop(0).close()
        self.cracks.append(mark)

    def start_shove(self, frm, to):
        if getattr(self, "life", None) is not None:
            self.life.cursor_hit()
        self.shove = [frm, self.world.clamp(*to), 0.0]

    def place(self):
        self.move(round(self.x - FX), round(self.y - FY))

    # ---- main loop
    def tick(self, dt=None):
        try:
            self._tick(dt)
        except Exception:  # noqa: BLE001 - one bad frame must not kill the dude
            self.errors += 1
            if self.errors <= 20:
                log(traceback.format_exc())

    def _tick(self, dt):
        now = self.clock()
        if dt is None:
            dt = min(max(now - self.last, 0.0), 0.05)
        self.last, self.dt = now, dt
        self.t += dt
        self.poll_hotkeys()
        self.handle_update(self.updater.step(self.t))
        if self.paused:
            return
        if now >= self.next_fs:
            self.next_fs = now + 0.5
            fs = self.w32.foreground_fullscreen()
            if fs != self.napping:
                self.napping = fs
                self.release_everything()
                self.sync_visible()
        if self.napping:
            return
        if now >= self.next_world:
            self.next_world = now + 0.15
            self.refresh_world(now)
        cur = self.w32.cursor_pos()
        self.rage = max(0.0, self.rage - self.tune.rage_cooldown_per_s * dt)
        self.attack_cd -= dt
        self.bazooka_cd -= dt
        self.katana_cd -= dt
        self.climb_cd -= dt
        self.st += dt
        self.shaker.step(dt)
        self.step_shove(dt)
        self.think(dt, cur)
        self.physics(dt, now)
        self.pose = self.life.adjust_pose(self.make_pose())
        if self.state == GRAB:
            self.hold_cursor(cur)
        for r in list(self.rockets):
            hit = r.step(dt, cur, self.world)
            if hit:
                self.rockets.remove(r)
                self.explode(*hit)
        self.booms = [b for b in self.booms if b.step(dt)]
        self.war.step(dt, cur, self.w32.buttons_down())
        self.terror.step(dt, cur, self.w32.buttons_down())
        self.arsenal.step(dt, cur, self.w32.buttons_down())
        self.life.step(dt, cur, self.w32.buttons_down())
        self.aqua.step(dt, cur, self.w32.buttons_down())
        self.vandal.step(dt, cur, self.w32.buttons_down())
        self.cracks = [c for c in self.cracks if c.step(dt)]
        self.fx = [(x, y, a + dt, k) for x, y, a, k in self.fx if a + dt < 0.6]
        self.place()
        self.update_clickable(cur)
        self.update()

    def refresh_world(self, now):
        if now >= self.next_screens:
            self.next_screens = now + 5.0
            self.world.refresh_screens()
        old = self.world.rect_of(self.plat_hwnd) if self.plat_hwnd else None
        self.world.refresh()
        if old and self.on_ground and self.state not in (HELD, "surf"):  # ride the window you drag
            new = self.world.rect_of(self.plat_hwnd)
            if new:
                self.x += new[0] - old[0]

    def poll_hotkeys(self):
        keys = self.w32.hotkeys()
        actions = {"q": self.quit, "p": self.toggle_pause, "w": self.enrage, "m": self.drop_mine, "f": self.drop_flak,
                   "t": self.terror_now, "a": self.weapon_now, "d": self.life.toggle_duel}
        for k, act in actions.items():
            down = k in keys
            if down and not self.keys_prev.get(k):
                act()
            self.keys_prev[k] = down

    # ---- AI
    def think(self, dt, cur):
        cx, cy = cur
        s = self.state
        dx = cx - self.x
        rel_y = cy - self.y  # negative = cursor above his feet
        dist = math.hypot(dx, cy - (self.y - 50))
        btn = self.w32.buttons_down()

        if self.vandal.think(dt, cur, btn):
            return
        if self.aqua.think(dt, cur, btn):
            return
        if self.life.think(dt, cur, btn):
            return
        if self.arsenal.think(dt, cur, btn):
            return
        if self.terror.think(dt, cur, btn):
            return
        if s == TANKING:
            return
        if s in (IDLE, WANDER, CHASE) and self.escalate(dt, cur):
            return
        if s == IDLE:
            self.vx = 0.0
            if self.st > self.state_len:
                self.pick_wander_target()
                self.set_state(WANDER, random.uniform(3, 7))
            self.maybe_aggro(dt, dist, btn)
            self.maybe_kick(dt)
        elif s == WANDER:
            d = self.target_x - self.x
            arrived = abs(d) < 10 and abs(self.y - self.target_y) < 40
            if arrived or self.st > self.state_len:
                self.set_state(IDLE, random.uniform(0.8, 2.5))
            else:
                if abs(d) > 10:
                    self.walk(math.copysign(self.wander_speed, d))
                else:
                    self.vx = 0.0
                self.navigate(self.target_x, self.target_y, dt)
            if self.state == WANDER and self.on_ground and random.random() < 0.12 * dt:
                self.jump(-random.uniform(700, 1000))
            self.maybe_aggro(dt, dist, btn)
            self.maybe_kick(dt)
        elif s == NOTICE:
            self.vx = 0.0
            self.f = 1 if dx >= 0 else -1
            if self.st > 0.45:
                self.set_state(CHASE, 7.0)
        elif s == CHASE:
            self.f = 1 if dx >= 0 else -1
            if abs(dx) > 14:
                self.walk(math.copysign(self.tune.chase(self.rage), dx))
            else:
                self.vx = 0.0
            in_reach = abs(dx) < 55 and -85 < rel_y < 10
            if self.can_slash(dt, dx, rel_y, btn):
                self.start_slash(cur)
            elif in_reach and not btn and self.attack_cd <= 0:
                if self.on_ground and random.random() < self.tune.grab(self.rage):
                    self.set_state(GRAB, 2.6)
                    self.struggle, self.grab_last, self.grab_dir = 0.0, None, -self.f
                else:
                    self.set_state(PUNCH, 0.38)
            else:
                self.navigate(cx, cy + 60, dt)
            if self.state == CHASE:
                if self.st > self.state_len or dist > 950:
                    self.attack_cd = 1.5
                    self.set_state(IDLE, 2.0)
                elif self.maybe_bazooka(dt * (4 if rel_y < -200 else 1), dist, btn):
                    pass
                elif rel_y < -320 and abs(dx) < 200 and self.on_ground and self.st > 1.5:
                    self.set_state(TAUNT, 1.2)
        elif s == PUNCH:
            self.vx *= 0.8
            if not self.hit_done and self.st > self.state_len * 0.45:
                self.hit_done = True
                hx, hy = self.limb("hand_a", pose_punch(1.0))
                if math.hypot(cx - hx, cy - hy) < 75 and not btn:
                    ang = math.atan2(cy - (self.y - 55), cx - self.x)
                    power = 90 + 120 * self.rage
                    self.start_shove(cur, (cx + math.cos(ang) * power, cy + math.sin(ang) * power - 20))
                    self.add_fx(cx, cy, "pow")
                    if random.random() < 0.4 + 0.6 * self.rage:
                        self.spawn_crack(cx, cy)
            if self.st > self.state_len:
                self.after_attack()
        elif s == GRAB:
            self.walk(self.grab_dir * 210)
            if self.blocked:
                self.grab_dir *= -1
            if self.on_ground and random.random() < 0.6 * dt:
                self.jump(-650)
            if btn:  # you're clicking: let go immediately
                self.attack_cd = 2.0
                self.set_state(IDLE, 1.0)
            elif self.struggle > 900:
                self.set_state(STUNNED, 1.3)
                self.add_fx(self.x, self.y - 100, "stars")
            elif self.st > self.state_len:  # yeet the cursor
                hx, hy = self.limb("hand_a")
                to = (hx + self.f * 240, hy - 160)
                self.start_shove((hx, hy), to)
                self.spawn_crack(*self.world.clamp(*to))
                self.after_attack()
        elif s == KICK:
            self.vx = 0.0
            if not self.hit_done and self.st > 0.45 * 0.4:
                self.hit_done = True
                if self.kick_target and self.shaker.shake(self.kick_target):
                    fx_, fy_ = self.limb("foot_a", pose_kick(1.0))
                    self.add_fx(fx_, fy_, "pow")
                    self.spawn_crack(fx_, fy_)
            if self.st > 0.45:
                self.after_attack()
        elif s == SLASH:
            k = self.st / self.state_len
            if 0.25 <= k < 0.45:
                self.vx = self.f * self.lunge_v
            else:
                self.vx *= max(0.0, 1 - 12 * dt)
            if not self.hit_done and k >= 0.47:
                self.hit_done = True
                self.terror.sfx.play("slash")
                self.slash_hit(cur, btn)
            if self.st > self.state_len:
                self.katana_cd = self.tune.katana_cooldown(self.rage)
                self.after_attack()
        elif s == CLIMB:
            self.vx, self.x = 0.0, self.climb_x
            self.vy = -self.tune.climb(self.rage)
            if self.y <= self.climb_top:
                self.y = self.climb_top
                if self.climb_hwnd:  # vault over the edge onto the window
                    self.vy, self.vx = -380.0, self.f * 170.0
                else:  # top of the screen edge: kick off the wall
                    self.vy, self.vx = -520.0, -self.f * 480.0
                    self.f = -self.f
                self.double_jumped, self.climb_cd = False, 1.2
                self.set_state(self.climb_return, self.climb_return_len)
            elif self.st > self.state_len or (self.climb_hwnd and not self.world.rect_of(self.climb_hwnd)):
                self.climb_cd = 1.2
                self.set_state(IDLE, 1.0)  # lost his grip
        elif s == AIM:
            self.vx = 0.0
            self.f = 1 if dx >= 0 else -1
            self.aim = self.aim_angle(cur)
            if self.st > self.state_len:
                self.fire(cur)
                self.set_state(RECOIL, 0.35)
        elif s == RECOIL:
            self.vx *= max(0.0, 1 - 8 * dt)
            if self.st > self.state_len:
                self.after_attack()
        elif s == TAUNT:
            self.vx = 0.0
            if self.st > self.state_len:
                chase = self.rage > self.tune.rage_chase_after_taunt
                self.set_state(CHASE if chase else IDLE, 4.0 if chase else 1.5)
        elif s == RAGDOLL:
            self.spin += self.spin_v * dt
            if self.on_ground and abs(self.vx) < 60 and self.st > 0.3:
                self.spin = 0.0
                self.set_state(GETUP, 0.45)
        elif s == GETUP:
            self.vx = 0.0
            if self.st > self.state_len:
                if self.rage > self.tune.rage_getup_notice:
                    self.set_state(NOTICE)
                    self.add_fx(self.x, self.y - 110, "!")
                else:
                    self.set_state(IDLE, 1.5)
        elif s == STUNNED:
            self.vx = 0.0
            if self.st > self.state_len:
                self.attack_cd = 3.0
                self.set_state(IDLE, 1.5)

    def escalate(self, dt, cur):
        kind = self.war.maybe_escalate(dt, cur, True)  # the tank parachutes in, so anywhere goes
        if kind == "tank":
            self.enter_tank()
        elif kind is not None:  # drones / airstrike: arms up, calling it in
            self.vx = 0.0
            self.set_state(TAUNT, 0.9)
            self.add_fx(self.x, self.y - 110, "!")
        return kind is not None

    def enter_tank(self):
        self.vx = 0.0
        self.set_state(TANKING, 999.0)
        self.hide()

    def start_tank(self):
        self.war.deploy_tank()
        self.enter_tank()

    def maybe_aggro(self, dt, dist, btn):
        if self.maybe_bazooka(dt, dist, btn):
            return
        if self.attack_cd > 0 or btn or dist > 450:
            return
        if random.random() < (0.2 + 1.3 * self.rage) * dt:
            self.set_state(NOTICE)
            self.add_fx(self.x, self.y - 110, "!")
            self.jump(-280)

    def can_slash(self, dt, dx, rel_y, btn):
        return (
            self.rage >= self.tune.rage_katana and self.katana_cd <= 0 and self.attack_cd <= 0 and self.on_ground
            and not btn and 40 < abs(dx) < 280 and -150 < rel_y < 30 and random.random() < 4 * dt
        )

    def start_slash(self, cur):
        dx = cur[0] - self.x
        self.f = 1 if dx >= 0 else -1
        self.lunge_v = min(max((abs(dx) - 60) / 0.12, 0.0), 1400.0)  # dash just into range
        self.kick_target = None
        self.set_state(SLASH, 0.6)

    def slash_hit(self, cur, btn):
        sx, sy = self.limb("shoulder", pose_slash(0.5))
        ang = math.atan2(0.6, 0.8 * self.f)  # down and forward
        hit = False
        dx, dy = cur[0] - sx, cur[1] - sy
        if not btn and -15 < dx * self.f < 130 and -120 < dy < 90:
            push = self.tune.slash(self.rage)
            self.start_shove(cur, (cur[0] + math.cos(ang) * push, cur[1] + math.sin(ang) * push))
            self.add_mark(Slash(cur[0], cur[1], ang))
            self.add_fx(cur[0], cur[1], "pow")
            hit = True
        tx, ty = sx + self.f * 85, sy + 20  # blade tip mid-swing
        hwnd = self.kick_target
        if hwnd is None:
            w = self.world.window_at(tx, ty)
            hwnd = w.hwnd if w else None
        self.kick_target = None
        if hwnd and self.shaker.slice(hwnd, self.f) and not hit:
            self.add_mark(Slash(tx, ty, ang))

    def navigate(self, tx, ty, dt):
        """Vertical route-finding toward a feet target: jump, climb, double jump, drop down."""
        up, dx = self.y - ty, tx - self.x
        can_climb = self.climb_cd <= 0
        near = self.world.wall_ahead(self.x, self.y, self.f) if up > 120 and can_climb else None
        if self.on_ground:
            self.double_jumped = False
            if up > 40:
                far = None
                if not near and can_climb and up > 330 and abs(dx) > 40:  # too high to jump: find a wall
                    far = self.world.wall_ahead(self.x, self.y, self.f, 320)
                if near:
                    self.start_climb(*near, ty)
                elif far:
                    self.vx = self.f * max(abs(self.vx), 160.0)
                elif abs(dx) < 340:
                    self.jump(-min(1300.0, math.sqrt(2 * G * (up + 30))))
            elif up < -40 and self.plat_hwnd and abs(dx) < 260:
                self.drop()
        elif near:  # grab the wall mid-air
            self.start_climb(*near, ty)
        elif not self.double_jumped and -150 < self.vy < 200 and up > 50:
            self.double_jumped = True
            self.vy = -850.0
            self.add_fx(self.x, self.y, "puff")

    def start_climb(self, side_x, top, hwnd, ty):
        self.climb_x = side_x - self.f * 8
        self.climb_top = top if top is not None else max(self.world.top + 120, ty)
        self.climb_hwnd = hwnd
        self.climb_return = self.state if self.state in (CHASE, WANDER) else IDLE
        self.climb_return_len = max(self.state_len - self.st, 1.5)
        self.on_ground, self.plat_hwnd = False, None
        self.set_state(CLIMB, 5.0)

    def pick_wander_target(self):
        w = self.world
        if w.plats and random.random() < 0.5:
            p = random.choice(w.plats)
            self.target_x, self.target_y = random.uniform(p.x1 + 15, p.x2 - 15), p.y
        else:
            self.target_x = random.uniform(w.left + 40, w.right - 40)
            self.target_y = w.floor_at(self.target_x)
        self.wander_speed = random.choice((120.0, 140.0, 230.0))

    def maybe_bazooka(self, dt, dist, btn):
        if self.rage < self.tune.rage_bazooka or self.bazooka_cd > 0 or not self.on_ground or btn or not 220 < dist < 1100:
            return False
        if random.random() >= (0.15 + 0.6 * self.rage) * dt:
            return False
        self.set_state(AIM, 0.75)
        self.add_fx(self.x, self.y - 110, "!")
        return True

    def aim_angle(self, cur):
        sx, sy = self.limb("shoulder", pose_aim(1.6))
        ang = math.atan2((cur[0] - sx) * self.f, cur[1] - sy)
        return min(max(ang, 0.5), math.pi - 0.15)

    def muzzle(self):
        sx, sy = self.limb("shoulder", pose_aim(self.aim))
        ux, uy = math.sin(self.aim) * self.f, math.cos(self.aim)
        return (sx + ux * 34, sy + uy * 34), (ux, uy)

    def fire(self, cur):
        (mx, my), (ux, uy) = self.muzzle()
        reach = max(60.0, math.hypot(cur[0] - mx, cur[1] - my))
        self.rockets.append(Rocket(mx, my, ux, uy, self.tune.rocket(self.rage), reach))
        self.add_fx(mx, my, "flash")
        self.terror.sfx.play("fire")
        self.vx = -self.f * 180.0
        self.bazooka_cd = self.tune.bazooka_cooldown(self.rage)

    def explode(self, x, y, hurt_cursor=True):
        self.war.on_explosion(x, y)
        self.booms.append(Boom(x, y))
        self.terror.sfx.play("boom")
        self.spawn_crack(x, y)
        cur = self.w32.cursor_pos()
        d = math.hypot(cur[0] - x, cur[1] - y)
        if hurt_cursor and d < 160 and not self.w32.buttons_down():
            ang = math.atan2(cur[1] - y, cur[0] - x) if d > 1 else random.uniform(0, math.tau)
            push = 120 + (160 - d) / 160 * 220
            self.start_shove(cur, (cur[0] + math.cos(ang) * push, cur[1] + math.sin(ang) * push))
        w = self.world.window_at(x, y)
        if w:
            self.shaker.shake(w.hwnd)
        hx, hy = self.limb("hip")
        if math.hypot(hx - x, hy - y) < 120 and self.state not in (HELD, TANKING):  # rocket jump, oops
            ang = math.atan2(hy - y, hx - x)
            self.vx, self.vy = math.cos(ang) * 700, min(-500.0, math.sin(ang) * 700)
            self.spin_v = random.choice((-10.0, 10.0))
            self.on_ground, self.plat_hwnd = False, None
            self.rage = min(1.0, self.rage + self.tune.rage_rocket_jump)
            self.set_state(RAGDOLL)
            self.terror.say("boom")
            self.life.dude_hit("boom")

    def maybe_kick(self, dt):
        if self.rage < self.tune.rage_kick or self.attack_cd > 0 or not self.on_ground:
            return
        if random.random() > self.tune.kick_chance(self.rage, dt):
            return
        tgt = self.plat_hwnd
        if not tgt:
            w = self.world.window_at(self.x + self.f * 45, self.y - 40)
            tgt = w.hwnd if w else None
        if tgt:
            self.kick_target = tgt
            if (
                self.rage > self.tune.rage_window_katana
                and self.katana_cd <= 0
                and random.random() < self.tune.window_katana_chance
            ):
                self.lunge_v = 0.0
                self.set_state(SLASH, 0.6)
            else:
                self.set_state(KICK, 0.45)

    def after_attack(self):
        self.attack_cd = self.tune.attack_pause(self.rage)
        if random.random() < self.rage:
            self.set_state(CHASE, 5.0)
        else:
            self.set_state(IDLE, random.uniform(1, 2))

    # ---- physics
    def physics(self, dt, now):
        if self.state == HELD:
            return
        if self.state == TANKING or self.state in self.terror.FROZEN or self.state in self.life.FROZEN or self.state in self.aqua.FROZEN or self.state in self.vandal.FROZEN:
            return
        if self.state == CLIMB:
            self.y += self.vy * dt
            self.on_ground = False
            return
        w = self.world
        self.blocked = False
        bounce = self.state == RAGDOLL
        if not self.on_ground:
            self.vy += G * dt
        elif self.state in (RAGDOLL, GETUP, STUNNED):
            self.vx *= max(0.0, 1 - 7 * dt)
        nx, ny = self.x + self.vx * dt, self.y + self.vy * dt
        if nx < w.left + 20 or nx > w.right - 20:
            nx = min(max(nx, w.left + 20), w.right - 20)
            self.vx = -self.vx * 0.5 if bounce else 0.0
            self.spin_v = -self.spin_v
            self.blocked = True
        if ny - 105 < w.top:
            ny = w.top + 105
            self.vy = abs(self.vy) * 0.3
        if self.on_ground:
            if self.plat_hwnd:
                p = w.plat(self.plat_hwnd, nx)
                if p:
                    ny, self.vy = p.y, 0.0
                else:
                    self.on_ground, self.plat_hwnd = False, None
            else:
                ny, self.vy = w.floor_at(nx), 0.0
        if not self.on_ground and self.vy >= 0:
            best, bp = w.floor_at(nx), None
            if now >= self.drop_until:
                for p in w.plats:
                    if p.x1 <= nx <= p.x2 and self.y <= p.y + 2 and ny >= p.y and p.y < best:
                        best, bp = p.y, p
            if ny >= best:
                ny = best
                if bounce and self.vy > 380:
                    self.vy = -self.vy * 0.38
                    self.vx *= 0.75
                    self.spin_v *= 0.6
                else:
                    self.vy, self.on_ground = 0.0, True
                    self.plat_hwnd = bp.hwnd if bp else None
        self.x, self.y = nx, ny
        if self.y > w.bottom + 300:  # fell out of the world somehow
            self.respawn()

    # ---- cursor control
    def step_shove(self, dt):
        if not self.shove:
            return
        if self.w32.buttons_down():
            self.shove = None
            return
        (sx, sy), (ex, ey), t = self.shove
        t += dt
        k = min(1.0, t / 0.14)
        e = 1 - (1 - k) ** 3
        self.w32.set_cursor(sx + (ex - sx) * e, sy + (ey - sy) * e)
        self.shove = None if k >= 1 else [(sx, sy), (ex, ey), t]

    def hold_cursor(self, cur):
        # Hard rule: never move the cursor while a mouse button is down. think()
        # already lets go when it sees a click, but it reads the buttons earlier in
        # the same tick, so check again right before the cursor is actually moved.
        if self.w32.buttons_down():
            self.grab_last = None
            return
        if self.grab_last is not None:
            d = math.hypot(cur[0] - self.grab_last[0], cur[1] - self.grab_last[1])
            if d > 6:
                self.struggle += d
        x, y = self.world.clamp(*self.limb("hand_a"))
        self.w32.set_cursor(x, y)
        self.grab_last = (int(x), int(y))

    def release_everything(self):
        self.war.clear()
        self.terror.release()
        self.arsenal.release()
        self.life.release()
        self.aqua.release()
        self.vandal.release()
        self.shaker.restore_all()
        self.shove = None
        for w in self.rockets + self.booms:
            w.close()
        self.rockets, self.booms = [], []
        if self.state in (GRAB, HELD, PUNCH, KICK, AIM, RECOIL, SLASH, CLIMB, TANKING):
            self.set_state(IDLE, 1.0)

    # ---- visuals
    def make_pose(self):
        s, st = self.state, self.st
        p = self.vandal.pose() or self.aqua.pose() or self.life.pose() or self.arsenal.pose()
        if p is not None:
            return p
        if s == HELD:
            return pose_held(self.t)
        if s == RAGDOLL:
            return pose_ragdoll(self.t, self.spin)
        if s == PUNCH:
            return pose_punch(st / self.state_len)
        if s == KICK:
            return pose_kick(st / 0.45)
        if s == "spray":
            return pose_spray(self.t)
        if s == "surf":
            return pose_surf(self.t)
        if s == "eat":
            return pose_eat(self.t)
        if s == "flee":
            self.phase += abs(self.vx) * self.dt / 22
            return pose_carry(self.phase)
        if s == SLASH:
            return pose_slash(st / self.state_len)
        if s == CLIMB:
            return pose_climb(self.t)
        if s in (AIM, RECOIL):
            return pose_aim(self.aim, 1.0 if s == RECOIL else 0.0)
        if s == TAUNT:
            return pose_taunt(self.t)
        if s == STUNNED:
            return pose_dizzy(self.t)
        if s == GETUP:
            return pose_crouch()
        if s == GRAB:
            self.phase += abs(self.vx) * self.dt / 22
            return pose_grab(self.phase)
        if not self.on_ground:
            return pose_air(self.vy, self.t)
        if abs(self.vx) > 5:
            self.phase += abs(self.vx) * self.dt / 22
            if abs(self.vx) > 200:
                return pose_walk(self.phase, 0.85, 0.25, 1.3)
            return pose_walk(self.phase, 0.5, 0.06, 0.5)
        return pose_stand(self.t)

    def update_clickable(self, cur):
        if self.state in (HELD, GRAB):
            want = True
        else:
            (hx, hy), (nx, ny) = self.limb("hip"), self.limb("neck")
            want = math.hypot(cur[0] - (hx + nx) / 2, cur[1] - (hy + ny) / 2) < 48
        if want != self.clickable:
            self.clickable = want
            self.w32.set_click_through(int(self.winId()), not want)

    def paintEvent(self, _):
        if self.life.hidden():
            return
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        r = min(self.rage, 1.0)
        color = self.life.tint(QColor(*(int(a + (b - a) * r) for a, b in zip(CALM, ANGRY))))
        lift = (1 - math.cos(self.pose.spin)) * 22 if self.pose.spin else 0.0
        self.draw_sheath(qp, lift)
        if self.state in (AIM, RECOIL):
            self.draw_bazooka(qp, lift)
        draw_dude(qp, FX, FY - lift, self.pose, self.f, color)
        self.life.paint(qp, FX, FY - lift, self.pose, self.f)
        self.aqua.paint(qp, FX, FY - lift, self.pose, self.f)
        self.vandal.paint(qp, FX, FY - lift, self.pose, self.f)
        if self.state == SLASH:
            self.draw_slash(qp)
        if self.state == "spray":
            self.draw_spray(qp, lift)
        if self.state == "wield":
            hx, hy = skeleton(self.pose, self.f)["hand_a"]
            self.arsenal.paint(qp, FX + hx, FY - lift + hy, self.f)
        ox, oy = self.x - FX, self.y - FY
        for x, y, a, kind in self.fx:
            lx, ly = x - ox, y - oy
            if kind == "pow":
                qp.setPen(QPen(QColor(255, 200, 40, int(255 * (1 - a / 0.6))), 3, Qt.SolidLine, Qt.RoundCap))
                for i in range(8):
                    ang = i * math.tau / 8
                    r0, r1 = 6 + a * 40, 14 + a * 60
                    qp.drawLine(
                        QPointF(lx + math.cos(ang) * r0, ly + math.sin(ang) * r0),
                        QPointF(lx + math.cos(ang) * r1, ly + math.sin(ang) * r1),
                    )
        for x, y, a, kind in self.fx:
            if kind == "flash" and a < 0.15:
                qp.setPen(Qt.NoPen)
                qp.setBrush(QColor(255, 220, 90, int(255 * (1 - a / 0.15))))
                qp.drawEllipse(QPointF(x - ox, y - oy), 14 - a * 50, 14 - a * 50)
                qp.setBrush(Qt.NoBrush)
            elif kind == "clang":
                qp.setPen(QPen(QColor(255, 245, 190, int(255 * (1 - a / 0.6))), 2.5, Qt.SolidLine, Qt.RoundCap))
                for i in range(7):
                    ang, r0 = i * math.tau / 7 + 0.4, 5 + a * 45
                    ca, sa = math.cos(ang), math.sin(ang)
                    qp.drawLine(
                        QPointF(x - ox + ca * r0, y - oy + sa * r0),
                        QPointF(x - ox + ca * (r0 + 9), y - oy + sa * (r0 + 9)),
                    )
            elif kind == "puff":
                qp.setPen(QPen(QColor(200, 200, 200, int(200 * (1 - a / 0.6))), 2))
                qp.drawEllipse(QPointF(x - ox, y - oy), 6 + a * 30, 3 + a * 12)
        hx, hy = skeleton(self.pose, self.f)["head"]
        hx, hy = FX + hx, FY - lift + hy
        if self.state == NOTICE:
            qp.setFont(QFont("Arial", 20, QFont.Black))
            qp.setPen(QColor(230, 40, 40))
            qp.drawText(QPointF(hx - 5, hy - 18), "!")
        if self.state == STUNNED:
            qp.setPen(Qt.NoPen)
            qp.setBrush(QColor(255, 210, 40))
            for i in range(3):
                ang = self.t * 6 + i * math.tau / 3
                qp.drawEllipse(QPointF(hx + math.cos(ang) * 16, hy - 14 + math.sin(ang) * 5), 3, 3)

    def draw_spray(self, qp, lift):
        hx, hy = skeleton(self.pose, self.f)["hand_a"]
        hx, hy = FX + hx, FY - lift + hy
        qp.setPen(QPen(QColor(255, 255, 255, 190), 1.5))
        qp.setBrush(QColor(200, 40, 60))
        qp.drawRoundedRect(QRectF(hx - 4, hy - 9, 8, 15), 2, 2)
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(230, 230, 230, 120))
        for i in range(6):
            k = (self.t * 3 + i / 6) % 1.0
            r = 2 + k * 5
            qp.drawEllipse(QPointF(hx + self.f * (8 + k * 40), hy - 6 + math.sin(i * 7.1) * k * 12), r, r)
        qp.setBrush(Qt.NoBrush)

    def draw_sheath(self, qp, lift):
        pts = skeleton(self.pose, self.f)
        (hx, hy), (nx, ny) = pts["hip"], pts["neck"]
        hx, hy, nx, ny = FX + hx, FY - lift + hy, FX + nx, FY - lift + ny
        tl = math.hypot(nx - hx, ny - hy) or 1.0
        tx, ty = (nx - hx) / tl, (ny - hy) / tl
        bx, by = ty * self.f, -tx * self.f  # points behind his back
        a = QPointF(hx + bx * 10, hy + by * 10)
        b = QPointF(nx + tx * 8 + bx * 3, ny + ty * 8 + by * 3)
        for w, col in ((7.5, QColor(255, 255, 255, 170)), (4.5, QColor(110, 20, 25))):
            qp.setPen(QPen(col, w, Qt.SolidLine, Qt.RoundCap))
            qp.drawLine(a, b)
        if self.state != SLASH:  # hilt sticking out over his shoulder
            dl = math.hypot(b.x() - a.x(), b.y() - a.y()) or 1.0
            ux, uy = (b.x() - a.x()) / dl, (b.y() - a.y()) / dl
            qp.setPen(QPen(QColor(25, 25, 25), 4, Qt.SolidLine, Qt.RoundCap))
            qp.drawLine(b, QPointF(b.x() + ux * 13, b.y() + uy * 13))
            qp.setPen(Qt.NoPen)
            qp.setBrush(QColor(170, 140, 60))
            qp.drawEllipse(b, 3.2, 3.2)
            qp.setBrush(Qt.NoBrush)

    def draw_slash(self, qp):
        k = self.st / self.state_len
        b = slash_blade(k)
        pts = skeleton(self.pose, self.f)
        if 0.35 <= k < 0.7:  # swoosh trail
            sx, sy = FX + pts["shoulder"][0], FY + pts["shoulder"][1]
            a0 = min(3.6, b + 1.4)
            trail = []
            for i in range(11):
                a = a0 + (b - a0) * i / 10
                trail.append(QPointF(sx + math.sin(a) * 74 * self.f, sy + math.cos(a) * 74))
            qp.setPen(QPen(QColor(255, 255, 255, 150), 6, Qt.SolidLine, Qt.RoundCap))
            qp.drawPolyline(QPolygonF(trail))
        draw_katana(qp, FX + pts["hand_a"][0], FY + pts["hand_a"][1], b, self.f)

    def draw_bazooka(self, qp, lift):
        sx, sy = skeleton(self.pose, self.f)["shoulder"]
        sx, sy = FX + sx, FY - lift + sy
        ux, uy = math.sin(self.aim) * self.f, math.cos(self.aim)
        a, b = QPointF(sx - ux * 16, sy - uy * 16), QPointF(sx + ux * 34, sy + uy * 34)
        for w, col in ((13, QColor(255, 255, 255, 190)), (9, QColor(70, 90, 45))):
            qp.setPen(QPen(col, w, Qt.SolidLine, Qt.FlatCap))
            qp.drawLine(a, b)
        qp.setPen(QPen(QColor(30, 35, 22), 11, Qt.SolidLine, Qt.FlatCap))
        qp.drawLine(QPointF(b.x() - ux * 5, b.y() - uy * 5), b)
        if self.state == AIM:  # laser sight: your warning to dodge
            alpha = int(170 + 70 * math.sin(self.t * 30))
            qp.setPen(QPen(QColor(255, 30, 30, alpha), 1.5, Qt.DashLine))
            qp.drawLine(b, QPointF(b.x() + ux * 90, b.y() + uy * 90))

    # ---- you vs him
    def try_parry(self, g):
        """Katana block: always mid-swing, sometimes when he's angry."""
        if not self.on_ground or self.state in (RAGDOLL, GETUP, STUNNED, HELD, CLIMB):
            return False
        if self.state != SLASH and (
            self.rage < self.tune.rage_parry_anytime or random.random() > self.tune.parry_chance
        ):
            return False
        self.add_fx(g.x(), g.y(), "clang")
        self.terror.sfx.play("clang")
        self.f = 1 if g.x() >= self.x else -1
        self.rage = min(1.0, self.rage + self.tune.rage_parry)
        self.kick_target, self.lunge_v = None, 0.0
        self.set_state(SLASH, 0.6)  # counter-attack
        return True

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        g = e.globalPosition()
        self.press = (g.x(), g.y())
        self.drag_off = (self.x - g.x(), self.y - g.y())
        self.samples.clear()

    def mouseMoveEvent(self, e):
        if not self.press:
            return
        g = e.globalPosition()
        if self.state != HELD and math.hypot(g.x() - self.press[0], g.y() - self.press[1]) > 6:
            self.set_state(HELD)
            self.shove, self.on_ground, self.plat_hwnd = None, False, None
        if self.state == HELD:
            nx, ny = g.x() + self.drag_off[0], g.y() + self.drag_off[1]
            if abs(nx - self.x) > 1:
                self.f = 1 if nx > self.x else -1
            self.x, self.y = nx, ny
            self.samples.append((self.clock(), nx, ny))
            self.place()

    def mouseReleaseEvent(self, e):
        if not self.press or e.button() != Qt.LeftButton:
            return
        g = e.globalPosition()
        self.press = None
        self.shove = None
        if self.state == HELD:  # throw
            vx = vy = 0.0
            if len(self.samples) >= 2:
                t1, x1, y1 = self.samples[-1]
                t0, x0, y0 = next(s for s in self.samples if t1 - s[0] <= 0.1)
                if t1 > t0:
                    vx, vy = (x1 - x0) / (t1 - t0), (y1 - y0) / (t1 - t0)
            spd = math.hypot(vx, vy)
            if spd > 2600:
                vx, vy = vx * 2600 / spd, vy * 2600 / spd
            self.vx, self.vy = vx, vy
            self.spin_v = vx / 120 + random.uniform(-3, 3)
            tn = self.tune
            self.rage = min(1.0, self.rage + tn.rage_throw + min(spd, 2600) / 2600 * tn.rage_throw_speed_bonus)
            self.terror.on_hit("thrown")
            self.life.dude_hit("thrown")
        else:  # punch
            if self.try_parry(g):
                return
            d = 1 if self.x >= g.x() else -1
            self.vx, self.vy, self.spin_v = 420.0 * d, -480.0, 9.0 * d
            self.rage = min(1.0, self.rage + self.tune.rage_punch)
            self.terror.on_hit("punched")
            self.life.dude_hit("punched")
            self.add_fx(g.x(), g.y(), "pow")
        self.on_ground, self.plat_hwnd, self.spin = False, None, 0.0
        self.set_state(RAGDOLL)

    # ---- app control
    def sync_visible(self):
        vis = not (self.paused or self.napping)
        self.setVisible(vis)
        for c in self.cracks:
            c.setVisible(vis)
        self.terror.set_visible(vis)
        self.arsenal.set_visible(vis)
        self.life.set_visible(vis)
        self.aqua.set_visible(vis)
        self.vandal.set_visible(vis)

    def toggle_pause(self):
        self.paused = not self.paused
        self.release_everything()
        self.sync_visible()
        self.last = self.clock()
        if self.tray:
            self.tray.pause_action.setText("Resume (Ctrl+Alt+P)" if self.paused else "Pause (Ctrl+Alt+P)")

    def drop_mine(self):
        if not (self.paused or self.napping):
            self.war.place_mine(self.w32.cursor_pos()[0])

    def drop_flak(self):
        if not (self.paused or self.napping):
            self.war.place_flak(self.w32.cursor_pos()[0])

    def handle_update(self, r):
        if r is None:
            return
        kind, ver, extra = r
        msg = {"uptodate": f"Je hebt de nieuwste versie ({ver}).",
               "available": f"Versie {ver} staat klaar. Klik hier om hem te downloaden.",
               "install": f"Updaten naar {ver}... ik ben zo terug, kanker.",
               "error": "Update-check mislukt, ik probeer het later nog eens."}[kind]
        self.update_url = extra if kind == "available" else None
        if self.tray:
            self.tray.showMessage("Desktop Dude", msg)
        if kind == "install":
            Updater.run_installer(extra)
            QTimer.singleShot(1500, self.quit)

    def weapon_now(self):
        if not (self.paused or self.napping):
            self.arsenal.start(self.arsenal.pick(self.w32.cursor_pos(), anything=True))

    def terror_now(self):
        if not (self.paused or self.napping):
            self.terror.trigger_random()

    def toggle_terror(self):
        self.terror.enabled = not self.terror.enabled
        if self.tray:
            self.tray.terror_action.setText("Terror mode: " + ("on" if self.terror.enabled else "off"))

    def toggle_sound(self):
        self.terror.sfx.muted = not self.terror.sfx.muted
        if self.tray:
            self.tray.sound_action.setText("Sound: " + ("off" if self.terror.sfx.muted else "on"))

    def clear_graffiti(self):
        self.terror.clear_graffiti()
        self.vandal.clear()

    def enrage(self):
        """Demo button: full rage, arsenal unlocked."""
        self.rage, self.attack_cd = 1.0, 0.0
        self.war.drone_cd, self.war.tank_cd, self.war.air_cd = 0.0, 3.0, 8.0
        self.terror.say("war")

    def toggle_war(self):
        self.war.enabled = not self.war.enabled
        if not self.war.enabled:
            self.release_everything()
            self.sync_visible()
        if self.tray:
            self.tray.war_action.setText("War mode: " + ("on" if self.war.enabled else "off"))

    def calm(self):
        self.rage = 0.0
        self.attack_cd = 5.0

    def reload_tuning(self):
        """Re-read the "tuning" block of dude_config.json without a restart (rage, terror and war)."""
        self.tune = self.terror.tune = self.war.tune = tuning.reload()
        if self.tray:
            self.tray.showMessage("Desktop Dude", "Tuning herladen uit dude_config.json.")
        return self.tune

    def quit(self):
        self.release_everything()
        for c in self.cracks:
            c.close()
        self.terror.close_all()
        if self.tray:
            self.tray.hide()
        log("quit")
        QApplication.quit()


def build_tray(dude: Dude):
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    qp = QPainter(pm)
    qp.setRenderHint(QPainter.Antialiasing)
    draw_dude(qp, 32, 60, pose_taunt(0.1), 1, QColor(*CALM), scale=0.5)
    qp.end()
    tray = QSystemTrayIcon(QIcon(pm))
    tray.setToolTip(f"Desktop Dude {VERSION}")
    menu = QMenu()
    tray.pause_action = QAction("Pause (Ctrl+Alt+P)", menu)
    tray.pause_action.triggered.connect(dude.toggle_pause)
    menu.addAction(tray.pause_action)
    for text, fn in (
        ("Calm him down", dude.calm),
        ("Enrage him: total war (Ctrl+Alt+W)", dude.enrage),
        ("War mode: on", dude.toggle_war),
        ("Terror now (Ctrl+Alt+T)", dude.terror_now),
        ("Random weapon (Ctrl+Alt+A)", dude.weapon_now),
        ("Duel! (Ctrl+Alt+D)", dude.life.toggle_duel),
        ("Summon mini-dudes", dude.life.spawn_minions),
        ("Clear graffiti", dude.clear_graffiti),
        ("Reload tuning", dude.reload_tuning),
        ("Terror mode: on", dude.toggle_terror),
        ("Sound: off", dude.toggle_sound),
        ("Respawn", dude.respawn),
        ("Quit (Ctrl+Alt+Q)", dude.quit),
    ):
        a = QAction(text, menu)
        a.triggered.connect(fn)
        menu.addAction(a)
        if text.startswith("War mode"):
            tray.war_action = a
        elif text.startswith("Terror mode"):
            tray.terror_action = a
        elif text.startswith("Sound"):
            tray.sound_action = a
    sub = menu.addMenu("Terror test")
    for kind, label in TERROR_MENU:
        act = QAction(label, sub)
        act.triggered.connect(lambda _=False, k=kind: dude.terror.trigger(k))
        sub.addAction(act)
    tray.terror_menu = sub
    wsub = menu.addMenu("Weapon test")
    for name, cfg in WEAPONS.items():
        act = QAction(cfg["label"], wsub)
        act.triggered.connect(lambda _=False, k=name: dude.arsenal.start(k))
        wsub.addAction(act)
    tray.weapon_menu = wsub
    lsub = menu.addMenu("Life test")
    for kind, label in (("watch", "Watch TV"), ("dance", "Dance"), ("sleep", "Sleep"), ("coffee", "Coffee"),
                        ("clock", "Sit on the clock"), ("start", "Kick the Start button"),
                        ("rain", "Rain shower"), ("snow", "Snow shower"), ("storm", "Thunderstorm"),
                        ("power", "Home Assistant light flicker")):
        act = QAction(label, lsub)
        act.triggered.connect(lambda _=False, k=kind: dude.life.trigger(k))
        lsub.addAction(act)
    tray.life_menu = lsub
    asub = menu.addMenu("Aquarium (Cuttlefish Pet)")
    for kind, label in (("ride", "Ride a cuttlefish"), ("carry", "Carry and throw one"), ("pet", "Pet one"),
                        ("fight", "Fight one"), ("eat", "Eat one (for real)")):
        act = QAction(label, asub)
        act.triggered.connect(lambda _=False, k=kind: dude.aqua.start(k))
        asub.addAction(act)
    tray.aqua_menu = asub
    vsub = menu.addMenu("Desktop vandalism")
    for kind, label in (("piece", "Graffiti on the wallpaper"), ("hole", "Punch a hole in the wallpaper"),
                        ("football", "Icon football")):
        act = QAction(label, vsub)
        act.triggered.connect(lambda _=False, k=kind: dude.vandal.start(k))
        vsub.addAction(act)
    tray.vandal_menu = vsub
    menu.addSeparator()
    for attr in ("life_action", "ears_action", "ha_action", "aqua_action"):
        info = QAction("", menu)
        info.setEnabled(False)
        menu.addAction(info)
        setattr(tray, attr, info)
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    li = QAction("Comment on videos/podcasts (local AI)", menu)
    li.setCheckable(True)
    li.setChecked(dude.life.ears.listen)
    li.toggled.connect(dude.life.ears.set_listen)
    menu.addAction(li)
    tray.listen_action = li
    menu.addSeparator()
    au = QAction("Auto-update", menu)
    au.setCheckable(True)
    au.setChecked(dude.updater.auto)
    au.toggled.connect(dude.updater.set_auto)
    menu.addAction(au)
    cu = QAction("Check for updates", menu)
    cu.triggered.connect(lambda: dude.updater.check(manual=True))
    menu.addAction(cu)
    tray.messageClicked.connect(lambda: dude.update_url and QDesktopServices.openUrl(QUrl(dude.update_url)))
    tray.update_actions = (au, cu)
    tray.setContextMenu(menu)
    tray.menu = menu
    tray.show()
    return tray


def render_pose_sheet(path):
    poses = [
        ("stand", pose_stand(0)),
        ("walk", pose_walk(1.0)),
        ("run", pose_walk(2.0, 0.85, 0.25, 1.3)),
        ("jump", pose_air(-1, 0)),
        ("fall", pose_air(1, 0.3)),
        ("punch windup", pose_punch(0.2)),
        ("punch", pose_punch(0.9)),
        ("kick windup", pose_kick(0.1)),
        ("kick", pose_kick(0.9)),
        ("grab", pose_grab(1.0)),
        ("taunt", pose_taunt(0.1)),
        ("ragdoll", pose_ragdoll(0.4, 2.2)),
        ("getup", pose_crouch()),
        ("dizzy", pose_dizzy(0.3)),
        ("held", pose_held(0.2)),
        ("bazooka", pose_aim(1.9)),
        ("slash windup", pose_slash(0.2)),
        ("slash", pose_slash(0.8)),
        ("climb", pose_climb(0.3)),
    ]
    cols = 5
    rows = math.ceil(len(poses) / cols)
    img = QImage(cols * 170, rows * 190, QImage.Format_ARGB32)
    img.fill(QColor(110, 130, 160))
    qp = QPainter(img)
    qp.setRenderHint(QPainter.Antialiasing)
    for i, (name, p) in enumerate(poses):
        cx, cy = (i % cols) * 170 + 85, (i // cols) * 190 + 150
        qp.setPen(QColor(60, 60, 60))
        qp.drawLine(cx - 70, cy, cx + 70, cy)
        draw_dude(qp, cx, cy, p, 1, QColor(*CALM))
        qp.setPen(QColor(255, 255, 255))
        qp.drawText(QPointF(cx - 60, cy + 25), name)
    qp.end()
    img.save(str(path))


def use_windows_certificates():
    """Verify TLS with Windows' own certificate store (like the browser does). Python's bundled view of it
    misses roots Windows only fetches on demand, e.g. Let's Encrypt's newer ones (open-meteo)."""
    try:
        import truststore

        truststore.inject_into_ssl()
        return True
    except Exception as e:  # noqa: BLE001 - not fatal: weather/updates just might fail
        log(f"truststore unavailable: {e!r}")
        return False


def selftest() -> int:
    """Used by build.ps1 on the frozen exe: can it do https (update checks, weather)?"""
    try:
        import ssl
        import urllib.request

        ssl.create_default_context()
        assert hasattr(urllib.request, "HTTPSHandler")
        assert use_windows_certificates(), "truststore"
        if getattr(sys, "frozen", False):  # the ears' heavy bits must have made it into the bundle
            import ctranslate2  # noqa: F401
            import soundcard  # noqa: F401
            from faster_whisper.vad import get_vad_model

            get_vad_model()
            import graffiti

            assert (graffiti.BASE / "assets" / "fonts" / graffiti.FONT_FILES["bubble"]).exists(), "fonts"
            # the graffiti helper process must start from the exe too (multiprocessing + freeze_support)
            from renderer import Renderer

            _app = QApplication.instance() or QApplication([])
            r = Renderer(True)
            r.start()
            jid, img, t0 = r.request(graffiti.Piece("tag", scale=0.5, seed=1)), None, time.time()
            while img is None and time.time() - t0 < 25:
                img = r.poll(jid)
                time.sleep(0.05)
            r.stop()
            assert img is not None and not img.isNull(), "graffiti helper"
        log(f"selftest ok: {ssl.OPENSSL_VERSION}")
        return 0
    except Exception as e:  # noqa: BLE001
        log(f"selftest FAILED: {e!r}")
        return 1


def main():
    import multiprocessing

    multiprocessing.freeze_support()  # the exe is also the graffiti helper process (renderer.py)
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if IS_WIN:
        use_windows_certificates()
    app = QApplication(sys.argv)
    if "--poses" in sys.argv:
        render_pose_sheet(Path("pose_sheet.png"))
        return
    app.setQuitOnLastWindowClosed(False)
    if not IS_WIN:
        log("not on Windows: running without real cursor/window control")
    dude = Dude(Win32() if IS_WIN else FakeWin32())
    dude.tray = build_tray(dude)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
