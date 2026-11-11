"""The macOS layer: the same interface as Win32 in desktop_dude.py, built on Quartz, Accessibility and AppKit.

What macOS allows, and what it asks you first:
- Reading the cursor, mouse buttons and the list of windows (positions only): no permission needed.
- Moving the cursor (he shoves it around): works out of the box.
- Moving other apps' windows (shake, surf): needs Accessibility (System Settings > Privacy & Security >
  Accessibility). macOS shows the prompt the first time he tries; without it he simply leaves windows alone.
- Ctrl+Option hotkeys: may need Input Monitoring. Everything is in the menu bar icon too.

Qt quirk handled here: on macOS a Qt.Tool window is an NSPanel that hides as soon as the app isn't active, and
the dude is never the active app. An app-wide event filter un-hides every overlay, puts it on all Spaces (also
over full-screen apps) and drops the wallpaper pieces to the desktop level, behind the icons.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import ApplicationServices as AS
import objc
import Quartz
from AppKit import NSApplication, NSScreen, NSWorkspace
from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QApplication, QWidget

from appdir import DATA


@dataclass
class WinInfo:  # same fields as desktop_dude.WinInfo
    hwnd: int
    rect: tuple[int, int, int, int]
    raw: tuple[int, int, int, int]
    zoomed: bool


def log(msg):
    try:
        with (DATA / "desktop_dude.log").open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass

SKIP_OWNERS = frozenset({"Dock", "Window Server", "SystemUIServer", "Control Center", "Notification Center",
                         "Spotlight", "WindowManager", "Wallpaper", "loginwindow", "Screenshot"})
# ANSI key codes for the Ctrl+Option hotkeys
KEYS = {"q": 0x0C, "p": 0x23, "w": 0x0D, "m": 0x2E, "f": 0x03, "t": 0x11, "a": 0x00, "d": 0x02}
STATE = Quartz.kCGEventSourceStateCombinedSessionState
# NSWindowCollectionBehavior: CanJoinAllSpaces | Stationary | IgnoresCycle | FullScreenAuxiliary
SPACES = (1 << 0) | (1 << 4) | (1 << 6) | (1 << 8)


def ns_window(win_id):
    """The NSWindow behind a Qt window id (Qt's winId on macOS is an NSView pointer)."""
    try:
        return objc.objc_object(c_void_p=int(win_id)).window()
    except Exception:  # noqa: BLE001
        return None


class _Overlays(QObject):
    """Every top-level window the dude shows: never hide on deactivate, live on every Space."""

    def __init__(self, mac):
        super().__init__()
        self.mac = mac

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Show and isinstance(obj, QWidget) and obj.isWindow():
            wid = int(obj.winId())
            QTimer.singleShot(0, lambda: self.mac.decorate(wid))  # after Qt has applied its own level
        return False


class MacOS:
    def __init__(self):
        self.pid = os.getpid()
        self.walls: set[int] = set()
        self.ax_cache: dict[int, object] = {}
        self.asked_ax = False
        self._front = None
        try:  # a menu bar app: no Dock icon, never steals focus
            NSApplication.sharedApplication().setActivationPolicy_(1)
        except Exception as e:  # noqa: BLE001
            log(f"mac: activation policy: {e!r}")
        app = QApplication.instance()
        self._filter = _Overlays(self)
        if app is not None:
            app.installEventFilter(self._filter)

    # ---- overlays
    def decorate(self, wid):
        w = ns_window(wid)
        if w is None:
            return
        try:
            if w.respondsToSelector_("setHidesOnDeactivate:"):
                w.setHidesOnDeactivate_(False)
            w.setCollectionBehavior_(SPACES)
            if wid in self.walls:
                w.setLevel_(Quartz.CGWindowLevelForKey(Quartz.kCGDesktopIconWindowLevelKey) - 1)
        except Exception as e:  # noqa: BLE001
            log(f"mac: decorate: {e!r}")

    # ---- input
    def cursor_pos(self):
        p = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
        return (int(p.x), int(p.y))

    def set_cursor(self, x, y):
        Quartz.CGWarpMouseCursorPosition((float(x), float(y)))
        Quartz.CGAssociateMouseAndMouseCursorPosition(True)  # no frozen cursor after a warp

    def buttons_down(self):
        return any(Quartz.CGEventSourceButtonState(STATE, b) for b in (0, 1, 2))

    def hotkeys(self):
        flags = Quartz.CGEventSourceFlagsState(STATE)
        if not (flags & Quartz.kCGEventFlagMaskControl and flags & Quartz.kCGEventFlagMaskAlternate):
            return set()
        return {k for k, code in KEYS.items() if Quartz.CGEventSourceKeyState(STATE, code)}

    def foreground_title(self):
        try:
            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            name = str(app.localizedName() or "")
            pid = app.processIdentifier()
            for info in self._list():  # window titles only come through with Screen Recording permission
                if info.get("kCGWindowOwnerPID") == pid and info.get("kCGWindowLayer", 1) == 0:
                    title = info.get("kCGWindowName")
                    return f"{title} - {name}" if title else name
            return name
        except Exception:  # noqa: BLE001
            return ""

    def taskbar_parts(self):
        return {}  # the Dock has no clock or Start button to sit on

    # ---- windows
    def _list(self):
        opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
        return Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []

    def _screens(self):
        """Screen frames and visible frames in top-left coordinates (what Quartz and Qt use)."""
        screens = NSScreen.screens()
        if not screens:
            return []
        main_h = screens[0].frame().size.height
        out = []
        for s in screens:
            f, v = s.frame(), s.visibleFrame()
            out.append(((f.origin.x, main_h - f.origin.y - f.size.height, f.size.width, f.size.height),
                        (v.origin.x, main_h - v.origin.y - v.size.height, v.size.width, v.size.height)))
        return out

    @staticmethod
    def _rect(info):
        b = info.get("kCGWindowBounds") or {}
        x, y, w, h = (int(b.get(k, 0)) for k in ("X", "Y", "Width", "Height"))
        return (x, y, x + w, y + h)

    def windows(self):
        out = []
        screens = self._screens()
        for info in self._list():  # front to back, like EnumWindows
            try:
                if info.get("kCGWindowLayer", 1) != 0 or info.get("kCGWindowOwnerPID") == self.pid:
                    continue
                if info.get("kCGWindowAlpha", 1) <= 0.01 or info.get("kCGWindowOwnerName") in SKIP_OWNERS:
                    continue
                l, t, r, b = self._rect(info)
                if r - l < 60 or b - t < 40:
                    continue
                zoomed = any(r - l >= vw - 8 and b - t >= vh - 8 for _f, (_vx, _vy, vw, vh) in screens)
                out.append(WinInfo(int(info["kCGWindowNumber"]), (l, t, r, b), (l, t, r, b), zoomed))
            except Exception:  # noqa: BLE001, S112 - one odd window must not break the list
                continue
        return out

    def _info(self, h):
        found = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionIncludingWindow, int(h)) or []
        return found[0] if found else None

    def window_rect(self, h):
        info = self._info(h)
        return self._rect(info) if info else None

    def is_zoomed(self, h):
        r = self.window_rect(h)
        if r is None:
            return False
        return any(r[2] - r[0] >= vw - 8 and r[3] - r[1] >= vh - 8 for _f, (_x, _y, vw, vh) in self._screens())

    def _ax_window(self, h):
        """The Accessibility handle of another app's window, matched by position and size."""
        if h in self.ax_cache:
            return self.ax_cache[h]
        if not AS.AXIsProcessTrusted():
            if not self.asked_ax:
                self.asked_ax = True
                AS.AXIsProcessTrustedWithOptions({AS.kAXTrustedCheckOptionPrompt: True})
                log("mac: asked for Accessibility (needed to move other apps' windows)")
            return None
        info = self._info(h)
        if not info:
            return None
        target = self._rect(info)
        app = AS.AXUIElementCreateApplication(info["kCGWindowOwnerPID"])
        err, wins = AS.AXUIElementCopyAttributeValue(app, AS.kAXWindowsAttribute, None)
        if err or not wins:
            return None
        for w in wins:
            e1, pos = AS.AXUIElementCopyAttributeValue(w, AS.kAXPositionAttribute, None)
            e2, size = AS.AXUIElementCopyAttributeValue(w, AS.kAXSizeAttribute, None)
            if e1 or e2:
                continue
            _, p = AS.AXValueGetValue(pos, AS.kAXValueCGPointType, None)
            _, s = AS.AXValueGetValue(size, AS.kAXValueCGSizeType, None)
            if abs(p.x - target[0]) < 3 and abs(p.y - target[1]) < 3 and abs(s.width - (target[2] - target[0])) < 3:
                self.ax_cache[h] = w
                return w
        return None

    def move_window(self, h, x, y):
        w = self._ax_window(h)
        if w is None:
            return
        try:
            AS.AXUIElementSetAttributeValue(w, AS.kAXPositionAttribute,
                                            AS.AXValueCreate(AS.kAXValueCGPointType, Quartz.CGPoint(x, y)))
        except Exception:  # noqa: BLE001
            self.ax_cache.pop(h, None)

    def bring_to_top(self, h):
        w = ns_window(h)  # only ever called for his own windows
        if w is not None:
            w.orderFrontRegardless()

    def is_layered(self, h):
        return True  # every Qt translucent window can be made click-through on macOS

    def set_click_through(self, h, on):
        w = ns_window(h)
        if w is None:
            return False
        w.setIgnoresMouseEvents_(bool(on))
        return True

    def foreground_fullscreen(self):
        try:
            pid = NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier()
            if pid == self.pid:
                return False
            frames = [f for f, _v in self._screens()]
            for info in self._list():
                if info.get("kCGWindowOwnerPID") == pid and info.get("kCGWindowLayer", 1) == 0:
                    l, t, r, b = self._rect(info)
                    return any(l <= fx + 1 and t <= fy + 1 and r >= fx + fw - 1 and b >= fy + fh - 1
                               for fx, fy, fw, fh in frames)
        except Exception:  # noqa: BLE001, S110 - can't tell: assume not full screen
            pass
        return False

    # ---- the wallpaper layer: a window level just below the desktop icons
    def wall_origin(self):
        return (0, 0)  # wall windows keep plain screen coordinates

    def wall_adopt(self, hwnd):
        self.walls.add(int(hwnd))
        w = ns_window(hwnd)
        if w is not None:
            w.setLevel_(Quartz.CGWindowLevelForKey(Quartz.kCGDesktopIconWindowLevelKey) - 1)
        return True

    def wallpaper_grab(self, x, y, w, h):
        return None  # icon football falls back to a plain patch (it needs the icon positions anyway)
