import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

import desktop_dude as dd


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_subtract_span():
    assert dd.subtract_span([(0, 100)], 20, 40) == [(0, 20), (40, 100)]
    assert dd.subtract_span([(0, 100)], -10, 200) == []
    assert dd.subtract_span([(0, 100)], 200, 300) == [(0, 100)]


def test_platforms_respect_occlusion():
    top = dd.WinInfo(1, (100, 100, 500, 400), (100, 100, 500, 400), False)
    under = dd.WinInfo(2, (300, 200, 900, 600), (300, 200, 900, 600), False)
    plats = dd.compute_platforms([top, under], top_limit=0)
    assert [(p.x1, p.x2, p.y) for p in plats if p.hwnd == 2] == [(500, 900, 200)]
    assert [(p.x1, p.x2, p.y) for p in plats if p.hwnd == 1] == [(100, 500, 100)]


def test_maximized_windows_are_not_platforms():
    w = dd.WinInfo(1, (0, 100, 1920, 1040), (0, 100, 1920, 1040), True)
    assert dd.compute_platforms([w], top_limit=0) == []


@pytest.mark.parametrize(
    "pose",
    [dd.pose_stand(0.3), dd.pose_walk(1.1), dd.pose_walk(2.5, 0.85, 0.25, 1.3), dd.pose_punch(0.9),
     dd.pose_kick(0.9), dd.pose_crouch(), dd.pose_taunt(0.2), dd.pose_aim(1.9),
     dd.pose_slash(0.2), dd.pose_slash(0.8), dd.pose_climb(0.3), dd.pose_spray(0.4)],
)
def test_feet_touch_ground(pose):
    pts = dd.skeleton(pose, 1)
    assert abs(max(pts["foot_a"][1], pts["foot_b"][1])) < 1e-6


def test_simulation_runs_and_restores_windows(app):
    dd.random.seed(7)
    w32 = dd.FakeWin32()
    clock = [0.0]
    dude = dd.Dude(w32, clock=lambda: clock[0])
    dude.timer.stop()
    seen = set()
    for i in range(60 * 60):
        clock[0] += 1 / 60
        t = clock[0]
        if i % 2 == 0:  # user wiggles near him, but he may move the cursor in between
            w32.cursor = (int(dude.x + 90 * math.sin(t * 0.8)), int(dude.y - 50 + 30 * math.sin(t * 1.7)))
        if i == 900:
            dude.rage = 1.0
        dude.tick(1 / 60)
        seen.add(dude.state)
    assert dude.errors == 0
    assert {dd.CHASE, dd.PUNCH} <= seen
    dude.release_everything()
    assert w32.pos == w32.orig  # every kicked window is back where it was
    dude.quit()


def test_throw_and_punch_by_user(app):
    w32 = dd.FakeWin32()
    clock = [0.0]
    dude = dd.Dude(w32, clock=lambda: clock[0])
    dude.timer.stop()
    dude.rage = 0.0
    # simulate a punch: press+release without moving
    dude.press = (dude.x - 10, dude.y - 50)

    class E:
        def __init__(self, x, y):
            self._p = dd.QPointF(x, y)

        def globalPosition(self):
            return self._p

        def button(self):
            return dd.Qt.LeftButton

    dude.mouseReleaseEvent(E(dude.x - 10, dude.y - 50))
    assert dude.state == dd.RAGDOLL and dude.vx > 0 and dude.rage > 0
    landed = False
    for _ in range(300):
        clock[0] += 1 / 60
        dude.tick(1 / 60)
        landed |= dude.state == dd.GETUP
        w = dude.world
        assert w.left <= dude.x <= w.right and dude.y <= w.bottom
    assert dude.errors == 0 and landed


def test_bazooka_fires_explodes_and_cleans_up(app):
    dd.random.seed(3)
    w32 = dd.FakeWin32()
    clock = [0.0]
    dude = dd.Dude(w32, clock=lambda: clock[0])
    dude.timer.stop()
    for _ in range(120):  # let him land
        clock[0] += 1 / 60
        dude.tick(1 / 60)
    target = dude.world.clamp(dude.x + 280, dude.y - 220)
    w32.cursor = (int(target[0]), int(target[1]))
    dude.rage = 1.0
    dude.set_state(dd.AIM, 0.75)
    booms = []
    real = dude.explode
    dude.explode = lambda x, y: (booms.append((x, y)), real(x, y))
    fired = False
    for _ in range(180):
        clock[0] += 1 / 60
        dude.tick(1 / 60)
        fired |= bool(dude.rockets)
    assert fired and booms and dude.errors == 0
    assert w32.cursor != (int(target[0]), int(target[1])) or len(booms) == 1
    dude.release_everything()
    assert not dude.rockets and not dude.booms
    assert w32.pos == w32.orig


class _Ev:
    def __init__(self, x, y):
        self._p = dd.QPointF(x, y)

    def globalPosition(self):
        return self._p

    def button(self):
        return dd.Qt.LeftButton


def _make(seed):
    dd.random.seed(seed)
    w32 = dd.FakeWin32()
    clock = [0.0]
    dude = dd.Dude(w32, clock=lambda: clock[0])
    dude.timer.stop()
    return w32, clock, dude


def _run(dude, clock, n):
    for _ in range(n):
        clock[0] += 1 / 60
        dude.tick(1 / 60)


def test_katana_slash_hits_cursor_and_restores(app):
    w32, clock, dude = _make(5)
    _run(dude, clock, 120)
    dude.rage, dude.attack_cd, dude.bazooka_cd = 1.0, 99.0, 99.0
    cur = tuple(int(v) for v in dude.world.clamp(dude.x + 150, dude.y - 60))
    w32.cursor = cur
    dude.start_slash(cur)
    _run(dude, clock, 40)
    assert dude.errors == 0
    assert w32.cursor != cur
    assert any(isinstance(m, dd.Slash) for m in dude.cracks)
    dude.release_everything()
    assert w32.pos == w32.orig


def test_parry_blocks_click(app):
    _w32, clock, dude = _make(6)
    _run(dude, clock, 120)
    dude.on_ground, dude.lunge_v = True, 0.0
    dude.set_state(dd.SLASH, 0.6)
    dude.press = (dude.x + 30, dude.y - 50)
    dude.mouseReleaseEvent(_Ev(dude.x + 30, dude.y - 50))
    assert dude.state == dd.SLASH and dude.st == 0.0


def test_climbs_onto_window(app):
    w32, clock, dude = _make(7)
    _run(dude, clock, 5)
    w32.cursor = (5, 5)
    dude.x, dude.y, dude.vx, dude.vy = 300.0, float(dude.world.floor_at(300)), 0.0, 0.0
    dude.on_ground, dude.plat_hwnd, dude.attack_cd = True, None, 99.0
    dude.target_x, dude.target_y, dude.wander_speed = 520.0, 220.0, 140.0
    dude.set_state(dd.WANDER, 8.0)
    reached, moves = False, set()
    for _ in range(60 * 6):
        clock[0] += 1 / 60
        dude.tick(1 / 60)
        moves.add(dude.state)
        if dude.on_ground and dude.plat_hwnd == 102:
            reached = True
            break
    assert dude.errors == 0
    assert reached, moves


def _spy_explode(dude):
    hits = []
    real = dude.explode

    def spy(x, y, **kw):
        hits.append((x, y))
        real(x, y, **kw)

    dude.explode = spy
    return hits


def test_drones_fire_and_get_shot_down(app):
    from warfare import BulletHole

    w32, clock, dude = _make(11)
    _run(dude, clock, 60)
    dude.attack_cd = dude.bazooka_cd = dude.katana_cd = 99.0
    dude.war.launch_drones(2)
    for _ in range(60 * 5):
        clock[0] += 1 / 60
        w32.cursor = (400, 400)
        dude.tick(1 / 60)
    assert any(isinstance(m, BulletHole) for m in dude.cracks)
    for drone in dude.war.drones:
        drone.hit = True
    _run(dude, clock, 60 * 3)
    assert not dude.war.drones and dude.errors == 0


def test_tank_shells_and_can_be_destroyed(app):
    w32, clock, dude = _make(12)
    _run(dude, clock, 120)
    hits = _spy_explode(dude)
    w32.cursor = tuple(int(v) for v in dude.world.clamp(dude.x + 350, 300))
    dude.start_tank()
    assert dude.state == dd.TANKING and not dude.isVisible()
    _run(dude, clock, 60 * 7)
    tank = dude.war.tank
    assert tank is not None and not tank.dropping
    assert hits
    tank.hits_pending = 3
    _run(dude, clock, 2)
    assert dude.war.tank is None and dude.state == dd.RAGDOLL and dude.isVisible()
    assert dude.errors == 0
    dude.release_everything()
    assert w32.pos == w32.orig


def test_airstrike_bombs_and_cleans_up(app):
    w32, clock, dude = _make(13)
    _run(dude, clock, 60)
    hits = _spy_explode(dude)
    w32.cursor = (400, 300)
    dude.war.call_airstrike(400)
    _run(dude, clock, 60 * 7)
    assert len(hits) >= 3
    assert dude.war.plane is None and not dude.war.projectiles
    assert dude.errors == 0
    dude.release_everything()
    assert w32.pos == w32.orig


def test_ceasefire_clears_everything(app):
    _w32, clock, dude = _make(14)
    _run(dude, clock, 60)
    dude.war.launch_drones(3)
    dude.start_tank()
    dude.war.call_airstrike(300)
    _run(dude, clock, 60 * 3)
    dude.release_everything()
    w = dude.war
    assert not (w.drones or w.projectiles or w.fx) and w.tank is None and w.plane is None
    assert dude.state != dd.TANKING and dude.errors == 0


def test_enrage_leads_to_war(app):
    w32, clock, dude = _make(15)
    _run(dude, clock, 60)
    dude.enrage()
    seen = set()
    for _ in range(60 * 15):
        clock[0] += 1 / 60
        w32.cursor = tuple(int(v) for v in dude.world.clamp(dude.x + 300, 350))
        dude.tick(1 / 60)
        dude.rage = 1.0
        w = dude.war
        seen |= {k for k, on in (("drones", w.drones), ("tank", w.tank), ("air", w.plane)) if on}
    assert {"drones", "tank"} <= seen
    assert dude.errors == 0


def test_mines_wreck_the_tank(app):
    w32, clock, dude = _make(21)
    _run(dude, clock, 60)
    dude.start_tank()
    _run(dude, clock, 60 * 5)
    tank = dude.war.tank
    assert tank is not None and not tank.dropping
    cur = (int(tank.x + 300 if tank.x < 400 else tank.x - 300), 300)  # keep the tank parked
    dude.war.place_mine(tank.x)
    dude.war.place_mine(tank.x + 10)
    for _ in range(90):
        clock[0] += 1 / 60
        w32.cursor = cur
        dude.tick(1 / 60)
    assert dude.war.tank is None and dude.state == dd.RAGDOLL
    assert not dude.war.mines and dude.errors == 0


def test_flak_shoots_down_drones(app):
    w32, clock, dude = _make(22)
    _run(dude, clock, 60)
    dude.attack_cd = dude.bazooka_cd = dude.katana_cd = 99.0
    dude.war.place_flak(150)
    dude.war.place_flak(650)
    dude.war.launch_drones(3)
    for _ in range(60 * 8):
        clock[0] += 1 / 60
        w32.cursor = (400, 400)
        dude.tick(1 / 60)
    assert not dude.war.drones and dude.errors == 0


def test_flak_shoots_down_the_bomber(app):
    w32, clock, dude = _make(24)
    _run(dude, clock, 60)
    dude.war.place_flak(100)
    dude.war.place_flak(700)
    dude.war.call_airstrike(400)
    plane = None
    for _ in range(60 * 7):
        clock[0] += 1 / 60
        w32.cursor = (400, 400)
        dude.tick(1 / 60)
        plane = plane or dude.war.plane
    assert plane is not None and plane.hp <= 0
    assert dude.war.plane is None and dude.errors == 0


def test_explosions_wreck_flak_and_mines_launch_the_dude(app):
    _w32, clock, dude = _make(23)
    _run(dude, clock, 60)
    dude.war.place_flak(300)
    f = dude.war.flaks[0]
    dude.explode(f.x, f.y - 30)
    _run(dude, clock, 2)
    assert not dude.war.flaks
    floor = dude.world.floor_at(500)
    dude.x, dude.y, dude.vx, dude.vy = 500.0, float(floor), 0.0, 0.0
    dude.on_ground, dude.plat_hwnd, dude.attack_cd = True, None, 99.0
    dude.set_state(dd.IDLE, 5.0)
    dude.war.place_mine(500)
    launched = False
    for _ in range(120):
        clock[0] += 1 / 60
        dude.tick(1 / 60)
        launched |= dude.state == dd.RAGDOLL
    assert launched and not dude.war.mines and dude.errors == 0


def test_terror_effects_run_and_clean_up(app):
    w32, clock, dude = _make(31)
    _run(dude, clock, 120)
    t = dude.terror
    t.enabled = False
    for kind in ("glass", "quake", "blackout", "popup", "graffiti"):
        assert t.trigger(kind), kind
        _run(dude, clock, 60 * 3)
    assert dude.errors == 0
    assert t.graffiti
    dude.release_everything()
    assert not t.fx and t.surf is None and t.steal is None and t.graffiti
    assert w32.pos == w32.orig


def test_graffiti_sticks_until_clicked(app):
    _w32, clock, dude = _make(32)
    _run(dude, clock, 60)
    t = dude.terror
    t.enabled = False
    assert t.trigger("graffiti")
    _run(dude, clock, 60 * 30)
    assert len(t.graffiti) == 1
    t.graffiti[0].mousePressEvent(_Ev(0, 0))
    _run(dude, clock, 60)
    assert not t.graffiti and dude.errors == 0


def _on_window_102(dude):
    dude.x, dude.y, dude.vx, dude.vy = 500.0, 220.0, 0.0, 0.0
    dude.on_ground, dude.plat_hwnd, dude.attack_cd = True, 102, 99.0
    dude.set_state(dd.IDLE, 5.0)


def test_window_surf_moves_window_and_snaps_back(app):
    w32, clock, dude = _make(33)
    dude.terror.enabled = False
    _run(dude, clock, 5)
    w32.cursor = (5, 5)
    _on_window_102(dude)
    assert dude.terror.trigger("surf")
    _run(dude, clock, 60)
    assert w32.pos[102] != w32.orig[102]
    _run(dude, clock, 60 * 6)
    assert w32.pos == w32.orig and dude.terror.surf is None and dude.errors == 0


def test_window_surf_lets_go_while_you_hold_a_button(app):
    w32, clock, dude = _make(37)
    dude.terror.enabled = False
    _run(dude, clock, 5)
    w32.cursor = (5, 5)
    _on_window_102(dude)
    assert dude.terror.trigger("surf")
    _run(dude, clock, 30)
    w32.buttons = True
    held = w32.pos[102]
    _run(dude, clock, 60)
    assert w32.pos[102] == held
    w32.buttons = False
    _run(dude, clock, 60 * 2)
    assert w32.pos == w32.orig and dude.errors == 0


def test_icon_kidnap_returns_when_you_hit_him(app):
    w32, clock, dude = _make(34)
    t = dude.terror
    t.enabled = False
    _run(dude, clock, 60)
    t.probe.icons = [("docs", (720, 20, 795, 95))]
    w32.cursor = (5, 5)
    assert t.trigger("steal")
    _run(dude, clock, 60)
    assert t.steal is not None and dude.state == "flee"
    dude.press = (dude.x - 10, dude.y - 50)
    dude.mouseReleaseEvent(_Ev(dude.x - 10, dude.y - 50))
    _run(dude, clock, 60 * 2)
    assert t.steal is None and dude.errors == 0


def test_cuttlefish_hunt_slashes_fish(app):
    from terror import Splash

    w32, clock, dude = _make(35)
    t = dude.terror
    t.enabled = False
    _run(dude, clock, 60)
    t.probe.fish = [(dude.x + 200, dude.world.floor_at(dude.x) - 80, 60, 50)]
    w32.cursor = (5, 5)
    assert t.trigger("hunt")
    splashed = False
    for _ in range(60 * 6):
        clock[0] += 1 / 60
        dude.tick(1 / 60)
        splashed |= any(isinstance(w, Splash) for w in t.fx)
    assert splashed and dude.errors == 0


def test_bored_dude_terrorizes_on_his_own(app):
    w32, clock, dude = _make(36)
    t = dude.terror
    t.cd = 0.0
    for _ in range(60 * 180):
        clock[0] += 1 / 60
        w32.cursor = (5, 5)
        dude.tick(1 / 60)
        dude.rage = 0.0
    assert t.count >= 1 and dude.errors == 0
    dude.release_everything()
    assert w32.pos == w32.orig


@pytest.mark.parametrize("name", list(__import__("arsenal").WEAPONS))
def test_every_weapon_works(app, name):
    from arsenal import WEAPONS

    w32, clock, dude = _make(40)
    dude.terror.enabled = dude.war.enabled = False
    _run(dude, clock, 90)
    dude.x = dude.world.left + 300.0
    dude.y, dude.vx, dude.vy = dude.world.floor_at(dude.x), 0.0, 0.0
    dude.on_ground, dude.plat_hwnd = True, None
    dude.set_state(dd.IDLE, 5.0)
    dude.attack_cd = dude.bazooka_cd = dude.katana_cd = 99.0
    kind = WEAPONS[name]["kind"]
    off = (60, -60) if kind == "melee" else (300, -150)
    start = tuple(int(v) for v in dude.world.clamp(dude.x + off[0], dude.y + off[1]))
    w32.cursor = start
    hits = _spy_explode(dude)
    ar = dude.arsenal
    assert ar.start(name) and dude.state == "wield"
    _run(dude, clock, 60 * 6)
    s = ar.stats
    if kind == "melee":
        assert s["swings"] == 1 and s["hits"] == 1 and w32.cursor != start
    elif kind == "gun":
        assert s["shots"] >= 1
    else:
        assert s["thrown"] == 1
    if name in ("grenade", "dynamite"):
        assert hits
    assert dude.errors == 0 and dude.state != "wield"
    dude.release_everything()
    assert w32.pos == w32.orig and not ar.items


def test_dude_grabs_weapons_when_chasing(app):
    w32, clock, dude = _make(41)
    dude.terror.enabled = dude.war.enabled = False
    _run(dude, clock, 60)
    dude.arsenal.cd = 0.0
    for _ in range(60 * 30):
        clock[0] += 1 / 60
        w32.cursor = tuple(int(v) for v in dude.world.clamp(dude.x + 200, dude.y - 60))
        dude.rage = 0.8
        dude.tick(1 / 60)
    assert dude.arsenal.count >= 1 and dude.errors == 0
    dude.release_everything()
    assert w32.pos == w32.orig


def test_held_mouse_button_blocks_weapon_fling(app):
    w32, clock, dude = _make(42)
    dude.terror.enabled = dude.war.enabled = False
    _run(dude, clock, 90)
    dude.x = dude.world.left + 300.0
    dude.y, dude.vx, dude.vy = dude.world.floor_at(dude.x), 0.0, 0.0
    dude.on_ground, dude.plat_hwnd = True, None
    dude.set_state(dd.IDLE, 5.0)
    start = tuple(int(v) for v in dude.world.clamp(dude.x + 60, dude.y - 60))
    w32.cursor = start
    w32.buttons = True
    dude.arsenal.start("bat")
    _run(dude, clock, 60 * 2)
    assert w32.cursor == start and dude.arsenal.stats["hits"] == 0


def test_dude_kills_and_eats_a_cuttlefish(app):
    from terror import DeadFish

    w32, clock, dude = _make(37)
    t = dude.terror
    t.enabled = dude.war.enabled = dude.arsenal.enabled = False
    _run(dude, clock, 60)
    t.probe.fish = [(dude.x + 200, dude.world.floor_at(dude.x) - 80, 60, 50)]
    w32.cursor = (5, 5)
    assert t.trigger("hunt")
    ate = False
    for _ in range(60 * 20):
        clock[0] += 1 / 60
        dude.tick(1 / 60)
        ate |= dude.state == "eat"
        if t.eaten:
            break
    assert ate and t.eaten == 1 and dude.errors == 0
    assert not any(isinstance(w, DeadFish) for w in t.fx)


def _grabbing(seed):
    w32, clock, dude = _make(seed)
    dude.terror.enabled = dude.war.enabled = dude.arsenal.enabled = False
    _run(dude, clock, 90)
    dude.x = dude.world.left + 400.0
    dude.y, dude.vx, dude.vy = dude.world.floor_at(dude.x), 0.0, 0.0
    dude.on_ground, dude.plat_hwnd = True, None
    dude.set_state(dd.GRAB, 2.6)
    dude.struggle, dude.grab_last, dude.grab_dir = 0.0, None, 1
    return w32, clock, dude


def test_grab_never_moves_the_cursor_while_a_button_is_down(app):
    w32, clock, dude = _grabbing(51)
    start = (dude.world.left + 900, dude.world.floor_at(dude.x) - 300)
    w32.cursor = start
    w32.buttons = True
    dude.hold_cursor(start)  # the last-moment check, even if think() missed the click
    assert w32.cursor == start
    _run(dude, clock, 60)
    assert w32.cursor == start
    assert dude.state != dd.GRAB and dude.errors == 0


def test_grab_holds_the_cursor_when_no_button_is_down(app):
    w32, _clock, dude = _grabbing(52)
    start = (dude.world.left + 900, dude.world.floor_at(dude.x) - 300)
    w32.cursor = start
    w32.buttons = False
    dude.hold_cursor(start)
    assert w32.cursor != start  # pulled to his hand, so the guard is not always on
    assert dude.grab_last == w32.cursor


def test_shove_stops_the_moment_a_button_goes_down(app):
    w32, clock, dude = _make(53)
    dude.terror.enabled = dude.war.enabled = dude.arsenal.enabled = False
    _run(dude, clock, 60)
    start = tuple(int(v) for v in dude.world.clamp(dude.x + 40, dude.y - 80))
    w32.cursor = start
    w32.buttons = True
    dude.start_shove(start, (start[0] + 240, start[1] - 160))
    _run(dude, clock, 30)
    assert w32.cursor == start and dude.shove is None