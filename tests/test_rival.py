import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import dataclasses

import pytest
from PySide6.QtWidgets import QApplication
from test_life import _quiet

import rival


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _tick(dude, clock, secs, until=None):
    for _ in range(int(secs * 60)):
        clock[0] += 1 / 60
        dude.tick(1 / 60)
        if until is not None and until():
            return True
    return until is None


def _setup(seed, **tune):
    rival._rng.seed(seed)
    w32, clock, dude = _quiet(seed)
    dude.aqua.enabled = False
    dude.tune = dataclasses.replace(dude.tune, **tune) if tune else dude.tune
    dude.rival.enabled = True  # off by default in the shared test helper
    dude.rival.cd = 0.0
    return w32, clock, dude


def _far(dude, w32):
    w32.cursor = (int(dude.world.right - 5), int(dude.world.top + 5))


def _near(dude, w32):
    w32.cursor = (int(dude.x + 20), int(dude.y - 60))


def _pester(dude, w32, clock, secs, until=None):
    """You, waving the cursor about on top of the dude."""
    for i in range(int(secs * 60)):
        w32.cursor = (int(dude.x + 20 + (i % 2) * 12), int(dude.y - 60))
        clock[0] += 1 / 60
        dude.tick(1 / 60)
        if until is not None and until():
            return True
    return until is None


def test_kees_only_comes_while_the_cursor_leaves_the_dude_alone(app):
    w32, clock, dude = _setup(1, rival_chance_per_s=50.0, rival_quiet_s=1.0)
    r = dude.rival
    _pester(dude, w32, clock, 4)
    assert r.kees is None, "turned up while you were waving the cursor at the dude"
    _far(dude, w32)
    assert _tick(dude, clock, 6, lambda: r.kees is not None)
    assert dude.state == rival.STATE
    r.release()


def test_a_fight_ends_in_a_knockout_and_kees_goes(app):
    w32, clock, dude = _setup(2, rival_rounds=1)
    r = dude.rival
    _far(dude, w32)
    assert r.start()
    assert _tick(dude, clock, 10, lambda: r.phase == "fight")
    assert _tick(dude, clock, 120, lambda: r.phase in ("after", "leave", ""))
    winner = r.winner
    assert winner in ("dude", "kees")
    loser_f = r.dude_f if winner == "kees" else r.kees_f
    assert loser_f.hp <= 0
    assert _tick(dude, clock, 40, lambda: r.kees is None), "Kees never left"
    assert dude.state != rival.STATE
    save = dude.life.save
    assert save["rival_won"] + save["rival_lost"] == 1
    assert save["rival_won" if winner == "dude" else "rival_lost"] == 1
    assert r.cd >= dude.tune.rival_cooldown_s[0]
    assert dude.errors == 0


def test_the_cursor_comes_first_and_kees_waits_his_turn(app):
    w32, clock, dude = _setup(3, rival_quiet_s=2.0)
    r = dude.rival
    _far(dude, w32)
    r.start()
    assert _tick(dude, clock, 10, lambda: r.phase == "fight")
    _tick(dude, clock, 1.0)
    assert _pester(dude, w32, clock, 3, lambda: r.phase == "wait")
    assert dude.state != rival.STATE, "still fighting while you are on him"
    _pester(dude, w32, clock, 1.0)
    assert r.kees is not None, "Kees should wait, not leave"
    _far(dude, w32)
    # the dude may still be dealing with the cursor for a moment; then the fight picks up again
    assert _tick(dude, clock, 15, lambda: r.phase == "fight" and dude.state == rival.STATE)
    r.release()
    assert dude.errors == 0


def test_kees_gives_up_if_you_keep_the_dude_busy(app):
    w32, clock, dude = _setup(4, rival_patience_s=5.0)
    r = dude.rival
    _far(dude, w32)
    r.start()
    assert _tick(dude, clock, 10, lambda: r.phase == "fight")
    assert _pester(dude, w32, clock, 20, lambda: r.phase == "leave" or r.kees is None)
    assert r.winner is None
    assert _pester(dude, w32, clock, 30, lambda: r.kees is None)
    assert dude.errors == 0


def test_clicking_kees_lands_one_on_him(app):
    w32, clock, dude = _setup(5)
    r = dude.rival
    _far(dude, w32)
    r.start()
    assert _tick(dude, clock, 10, lambda: r.phase == "fight" and r.kees_f.phase == "ok")
    hp = r.kees_f.hp
    r.kees.punched = True
    _tick(dude, clock, 1 / 60)
    assert r.kees_f.hp < hp
    assert r.kees_f.phase in ("down", "ko")
    r.release()


def test_a_parked_cursor_is_not_pestering(app):
    """An arrow left lying on top of the dude is not you bothering him: Kees still comes."""
    w32, clock, dude = _setup(6, rival_chance_per_s=50.0, rival_quiet_s=1.0)
    _near(dude, w32)
    assert _tick(dude, clock, 12, lambda: dude.rival.kees is not None)
    dude.rival.release()


def test_a_match_is_best_of_three(app):
    w32, clock, dude = _setup(21)
    r = dude.rival
    _far(dude, w32)
    r.start()
    rounds_seen = set()

    def over():
        rounds_seen.add(r.round)
        return r.phase == "leave" or r.kees is None

    assert _tick(dude, clock, 400, over), f"match never ended (phase {r.phase}, score {r.score})"
    assert max(r.score.values()) == 2, r.score
    assert min(r.score.values()) <= 1, r.score
    assert len(rounds_seen) >= 2, "never got past round one"
    assert r.winner == max(r.score, key=r.score.get)
    save = dude.life.save
    assert save["rival_won"] + save["rival_lost"] == 1, "a match counts once, not once per round"
    assert _tick(dude, clock, 40, lambda: r.kees is None)
    assert dude.errors == 0


def test_kees_is_the_dudes_usual_company(app):
    """Left alone for ten minutes, the dude spends most of it fighting Kees."""
    w32, clock, dude = _setup(31)
    dude.rival.cd = dude.tune.rival_first_delay_s
    _far(dude, w32)
    fighting = visits = 0
    was = False
    for _ in range(600 * 60):
        clock[0] += 1 / 60
        dude.tick(1 / 60)
        now = dude.rival.kees is not None
        visits += now and not was
        fighting += now
        was = now
    share = fighting / (600 * 60)
    assert visits >= 4, f"only {visits} visits in ten minutes"
    assert share > 0.45, f"Kees was around only {share:.0%} of the time"
    assert dude.errors == 0
    dude.rival.release()


@pytest.mark.parametrize("seed", [11, 12, 13])
def test_fights_always_finish_without_errors(app, seed):
    w32, clock, dude = _setup(seed)
    r = dude.rival
    _far(dude, w32)
    r.start()
    assert _tick(dude, clock, 450, lambda: r.kees is None), f"fight {seed} never ended (phase {r.phase})"
    assert dude.errors == 0
    assert dude.state != rival.STATE
