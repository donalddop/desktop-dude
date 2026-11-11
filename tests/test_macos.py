"""The macOS layer against a real Mac (GitHub's macOS runners have a desktop session). Skipped elsewhere."""

import os
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin" or os.environ.get("QT_QPA_PLATFORM") == "offscreen",
                                reason="macOS with its real desktop only")


@pytest.fixture(scope="module")
def mac():
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from macos import MacOS

    return MacOS()


def test_cursor_round_trip(mac):
    x, y = mac.cursor_pos()
    mac.set_cursor(x + 7, y + 5)
    nx, ny = mac.cursor_pos()
    mac.set_cursor(x, y)
    assert abs(nx - (x + 7)) <= 1 and abs(ny - (y + 5)) <= 1


def test_reads_the_desktop(mac):
    wins = mac.windows()
    for w in wins:
        l, t, r, b = w.rect
        assert r > l and b > t and w.hwnd > 0
    assert isinstance(mac.buttons_down(), bool)
    assert isinstance(mac.hotkeys(), set)
    assert isinstance(mac.foreground_title(), str)
    assert isinstance(mac.foreground_fullscreen(), bool)
    assert mac.taskbar_parts() == {}
    assert mac.wall_origin() == (0, 0)


def test_dude_runs_on_the_mac_layer(mac):
    import desktop_dude as dd

    dude = dd.Dude(mac)
    try:
        for _ in range(120):
            dude.tick(1 / 60)
        assert dude.errors == 0
    finally:
        dude.release_everything()
        dude.vandal.stop()
        dude.close()
