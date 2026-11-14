"""Kees, the rival: another stick figure the dude is more or less always at war with.

Whenever you leave the dude alone for a bit, Kees is never far away. The two square up, talk some trash and
then properly fight: jabs, kicks, uppercuts, dropkicks, blocks, little HP bars. A visit is a match, best of
three by default: after a knockout the loser gets up, they catch their breath, and it is round two -- the
rounds each of them has won show as gold pips under his HP bar. Whoever takes the match gloats, the loser
gets up dizzy, Kees walks (or limps) off, and before long he is back for the rematch.

You always come first. Bring the cursor near the dude, click him or pick him up and he drops the fight to
deal with you; Kees waits on the side with his arms folded, and gives up and leaves if you keep the dude
busy for too long. Click Kees yourself to give him one on the nose.

House rules: a window one of them gets knocked into shakes and snaps back (Shaker), nothing else is touched,
and the only thing remembered is the score, in the dude's own save game.
"""

from __future__ import annotations

import dataclasses
import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen

from arsenal import PopText
from terror import LINES, Bubble
from warfare import FxWindow, _painter

G = 2400.0
W, H, FX, FY = 240, 210, 120, 165  # Kees's window and his feet inside it, same as the dude's
COLOR = QColor(226, 108, 20)  # oranje
CAP = QColor(22, 30, 58)
STATE = "rival"
# The dude is busy with your cursor in any of these.
HOSTILE = ("notice", "chase", "punch", "grab", "aim", "recoil", "slash", "held", "ragdoll", "getup", "taunt")
# Whether you are bothering him is about what *you* do, not where the arrow happens to be: the dude goes after
# a parked cursor on his own when he is bored, and walking up to it himself is not you terrorising him. So it
# counts while the cursor is moving near him, a button is down, or he is being held or thrown. A chase he
# started himself, Kees can cut in on -- the dude will gladly take a real fight over an arrow in a corner.
THROWN = ("held", "ragdoll")
INTERRUPTIBLE = ("idle", "wander", "chase")
STILL_S = 2.0  # a cursor that has not moved for this long is parked, not pestering

_rng = random.Random()

# What the dude says. Kees has his own lines below, in his own bubble.
LINES.update({
    "rival_in": ["Kees. Natuurlijk. Wie anders", "Jij weer? Heb je vorige keer niet genoeg gehad?",
                 "Mijn desktop, mijn regels, Kees", "Kom maar op dan, oranje klapstuk"],
    "rival_win": ["En blijf liggen!", "Doei Kees! Groetjes thuis", "Wie is de baas? IK ben de baas",
                  "Was dat alles? Mijn oma slaat harder"],
    "rival_lose": ["Ik... gleed uit", "Geluksstoot. Volgende keer ben je de sjaak",
                   "Au. Au au au.", "Dit vertel je aan niemand, Kees"],
    "rival_help": ["HAHA, dank je!", "Ja! Pak hem!", "Zie je, de cursor staat aan MIJN kant"],
    "rival_round": ["Nog een rondje dan", "Ronde twee, Kees. Nu echt", "Opstaan en doorgaan",
                    "Ik was nog aan het opwarmen", "Kom maar, ik heb tijd"],
    "rival_round_win": ["Die zat!", "Een-nul, Kees", "Lekker hoor", "Blijf maar even liggen"],
    "rival_round_lose": ["Die telde niet", "Ik liet je winnen", "Oké, nu wordt het menens"],
})

KEES = {
    "in": ["Ey. Jij daar. Op MIJN scherm?", "Tijd voor ronde zoveel, mattie", "Ik kom even je dag verpesten",
           "Wat sta je nou te kijken? Kom dan!"],
    "hit": ["Ooh!", "Dat voelde je!", "Ja toch!", "Pak aan!"],
    "win": ["Weer gewonnen. Saai hoor", "Ik ben de echte Desktop Dude", "Tot de volgende, kneus",
            "Je leert het nooit, hè?"],
    "lose": ["Ik kom terug... met een grotere broer", "Dit was een oefenronde!", "Mijn pet zat scheef",
             "Au. Oké. Volgende keer."],
    "wait": ["Ik wacht wel. Doe jij maar.", "Hé! We waren bezig!", "Laat die cursor, we zijn aan het vechten!",
             "Ik heb de hele dag, hoor"],
    "bored": ["Laat maar. Jij hebt al genoeg aan je hoofd", "Pff. Ik kom wel een andere keer", "Saai. Later, mattie"],
    "help": ["Twee tegen één? Laf!", "Hé, wie sloeg dat?!", "Bemoei je er niet mee!"],
    "round": ["Volgende ronde, mattie", "Nu ben ik warm", "Die eerste was gratis", "Nog eentje. Kom."],
    "round_win": ["Eentje voor Kees!", "Voel je hem al?", "En dat was nog maar één"],
}

# One table for both fighters. `hit` is when in the move the blow lands, as a fraction of `len`.
MOVES = {
    "punch": {"len": 0.36, "hit": 0.45, "reach": 66, "dmg": 9, "knock": 260, "down": False, "y": 72},
    "kick": {"len": 0.46, "hit": 0.42, "reach": 80, "dmg": 12, "knock": 380, "down": False, "y": 50},
    "uppercut": {"len": 0.50, "hit": 0.52, "reach": 56, "dmg": 16, "knock": 420, "down": True, "y": 95},
    "dropkick": {"len": 0.95, "hit": None, "reach": 70, "dmg": 14, "knock": 600, "down": True, "y": 60},
    "block": {"len": 0.55},
    "taunt": {"len": 0.9},
}
WORDS = ["BAM!", "POW!", "TOK!", "PATS!", "BOEF!", "KLETS!"]


# --------------------------------------------------------------------------- poses


def pose_guard(P, t):
    b = math.sin(t * 8) * 0.06
    return P(0.12, (0.35 + b, -0.3), (0.1, -0.45), (0.9, 0.55), (2.6, 2.4))


def pose_block(P):
    return P(-0.12, (0.3, -0.3), (0.1, -0.4), (1.35, 1.1), (2.95, 2.8))


def pose_flinch(P):
    return P(-0.4, (0.1, -0.4), (0.0, -0.3), (-0.6, 0.9), (-0.2, 1.5))


def pose_uppercut(P, k):
    if k < 0.45:
        return P(0.35, (0.9, -0.2), (-0.4, -0.6), (0.3, -0.6), (1.8, 0.8))
    return P(-0.15, (0.2, -0.3), (0.05, -0.4), (2.9, -0.4), (3.1, 0.6))


def pose_dropkick(P):
    return P(-0.6, (1.6, -0.4), (1.6, -0.9), (-1.2, 2.2), (-0.8, 2.6))


def pose_victory(P, t):
    w = math.sin(t * 12) * 0.25
    return P(-0.05, (0.15, -0.15), (0.05, -0.05), (2.8 + w, -2.8 + w), (3.1 + w, -3.1 + w))


def pose_folded(P, t):
    b = math.sin(t * 2) * 0.03
    return P(-0.04 + b, (0.12, -0.12), (0.06, -0.06), (0.55, -0.45), (1.9, -1.8))


@dataclasses.dataclass
class Fighter:
    """One side of the fight. The body it moves is the dude himself or Kees: both have x, y, vx, vy, f, on_ground."""

    hp: float = 100.0
    max_hp: float = 100.0
    move: str | None = None
    mt: float = 0.0
    hit_done: bool = False
    move_id: int = 0
    saw: int = -1  # the opponent's move_id this fighter already decided whether to block
    phase: str = "ok"  # ok | down | getup | ko
    pt: float = 0.0
    flinch: float = 0.0
    cd: float = 0.6
    spin: float = 0.0
    spin_v: float = 0.0
    guard: float = 0.35  # chance to block a blow it sees coming
    combo: int = 0  # clean hits taken in a row: the third one puts you down
    walk_ph: float = 0.0
    below: float = 0.0  # how long the other one has been up on a ledge above this one


# --------------------------------------------------------------------------- Kees himself


class Kees(FxWindow):
    """The rival: a full-size stick figure in orange with his cap on backwards."""

    def __init__(self, rival, x, y, f):
        super().__init__(W, H, clickable=True)
        self.rival, self.x, self.y, self.f = rival, x, y, f
        self.vx = self.vy = 0.0
        self.on_ground, self.drop_until = False, 0.0
        self.pose, self.punched = None, False
        self.place()
        self.show()

    def place(self):
        self.move(round(self.x - FX), round(self.y - FY))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.punched = True

    def physics(self, dt, world, now):
        prev = self.y
        if not self.on_ground:
            self.vy += G * dt
        nx, ny = self.x + self.vx * dt, self.y + self.vy * dt
        inside = world.left + 20 <= self.x <= world.right - 20
        # Coming in from off-screen or walking off it is allowed; once in, the screen edges are walls.
        if inside and self.rival.phase != "leave" and not world.left + 20 <= nx <= world.right - 20:
            nx = min(max(nx, world.left + 20), world.right - 20)
            self.vx = -self.vx * 0.4
        if ny - 105 < world.top:
            ny, self.vy = world.top + 105, abs(self.vy) * 0.3
        fx = min(max(nx, world.left + 1), world.right - 1)
        ground = world.floor_at(fx)
        if now >= self.drop_until:
            for p in world.plats:  # land on (or keep standing on) a window top
                if p.x1 <= nx <= p.x2 and prev <= p.y + 2 and ny >= p.y and p.y < ground:
                    ground = p.y
        if ny >= ground and self.vy >= 0:
            ny, self.vy, self.on_ground = ground, 0.0, True
        else:
            self.on_ground = False
        self.x, self.y = nx, ny

    def paintEvent(self, _):
        if self.pose is None:
            return
        qp = _painter(self)
        k = self.rival.kit
        lift = (1 - math.cos(self.pose.spin)) * 22 if self.pose.spin else 0.0
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(0, 0, 0, 1))  # invisible, but makes the body clickable
        qp.drawEllipse(QPointF(FX, FY - 60 - lift), 26, 58)
        k["draw"](qp, FX, FY - lift, self.pose, self.f, COLOR)
        hx, hy = k["skeleton"](self.pose, self.f)["head"]
        self.paint_cap(qp, FX + hx, FY - lift + hy)
        r = self.rival
        if r.phase in ("fight", "standoff", "after") and r.kees_f is not None:
            r.paint_hp(qp, FX, FY - lift + hy - 34, r.kees_f, r.score["kees"], r.tune.rival_rounds)
        if r.kees_f is not None and r.kees_f.phase == "ko" or (r.phase == "after" and r.winner == "dude"):
            r.paint_stars(qp, FX + hx, FY - lift + hy)

    def paint_cap(self, qp, hx, hy):
        """A cap on backwards: a dome over the top of the head, the peak sticking out behind."""
        qp.save()
        qp.translate(hx, hy)
        qp.rotate(math.degrees(self.pose.spin))
        f = self.f
        dome = QPainterPath()  # sits high enough to leave his eye showing
        dome.moveTo(-12.5, -4.5)
        dome.arcTo(QRectF(-12.5, -16.5, 25, 24), 180, -180)
        dome.closeSubpath()
        peak = QPainterPath()  # the peak points backwards, away from where he looks
        peak.addRoundedRect(QRectF(-22, -7.5, 12, 5) if f > 0 else QRectF(10, -7.5, 12, 5), 2.5, 2.5)
        for w, col in ((3.5, QColor(255, 255, 255, 190)), (0.0, CAP)):
            qp.setPen(QPen(col, w) if w else Qt.NoPen)
            qp.setBrush(CAP)
            qp.drawPath(dome)
            qp.drawPath(peak)
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(255, 255, 255))
        qp.drawEllipse(QPointF(-f * 1.5, -16), 2.0, 2.0)  # the button on top
        qp.restore()


# --------------------------------------------------------------------------- the fight


class Rival:
    def __init__(self, dude, kit, real):
        self.d, self.kit, self.real = dude, kit, real
        self.P = kit["Pose"]
        self.enabled = True
        self.kees: Kees | None = None
        self.phase, self.pt = "", 0.0
        self.dude_f: Fighter | None = None
        self.kees_f: Fighter | None = None
        self.winner = None
        self.fx: list = []
        self.bubble: Bubble | None = None
        self.quiet_for = 0.0
        self.waited = 0.0
        self.dropped = False
        self.forced = False  # called from the tray: come as soon as the dude is free
        self.since_hit = 0.0  # fight time since a blow last landed or was blocked
        self.cd = self.tune.rival_first_delay_s
        self._said_wait = False
        self.score = {"dude": 0, "kees": 0}  # rounds won this visit
        self.round = 1
        self._cur = None
        self.cur_still = 0.0  # seconds since the cursor last moved
        self.due = False

    @property
    def tune(self):
        return self.d.tune

    @property
    def active(self):
        return self.kees is not None

    # ---- when
    def quiet(self, cur, btn, near=300.0):
        """Are you leaving the dude alone?"""
        d = self.d
        dist = math.hypot(cur[0] - d.x, cur[1] - (d.y - 50))
        pestering = dist <= near and self.cur_still < STILL_S
        return not btn and not pestering and d.press is None and d.state not in THROWN

    def track_cursor(self, cur, dt):
        if self._cur is None or math.hypot(cur[0] - self._cur[0], cur[1] - self._cur[1]) > 3:
            self.cur_still = 0.0
        else:
            self.cur_still += dt
        self._cur = (cur[0], cur[1])

    def busy(self):
        d = self.d
        war = d.war
        return bool(d.life.duel is not None or getattr(war, "drones", None) or getattr(war, "tank", None)
                    or getattr(war, "plane", None) or d.crew.active)

    def request(self):
        """From the tray: Kees comes as soon as the dude is standing about, cursor or no cursor."""
        if self.kees is None:
            self.forced = True

    def can_start(self, dt):
        d = self.d
        life = d.life
        # You are watching something and he has not sat down with his popcorn yet: that comes first.
        if not self.forced and life.app() == "watch" and life.cd.get("watch", 1.0) <= 0:
            return False
        if not self.forced:
            if not (self.enabled and self.cd <= 0 and self.quiet_for >= self.tune.rival_quiet_s):
                self.due = False
                return False
            if not self.due:
                if _rng.random() >= self.tune.rival_chance_per_s * dt:
                    return False
                self.due = True  # Kees is on his way: from here on it is only a matter of the dude being free
        if self.busy():
            return False
        if d.state in ("chase", "climb"):
            # He is off after an arrow nobody is waving at him: let it go and come down for Kees.
            d.set_state("idle", 0.6)
        return d.state in INTERRUPTIBLE and d.on_ground

    def start(self) -> bool:
        """Kees turns up: runs in from the side away from the cursor, or drops in from above."""
        d = self.d
        if self.kees is not None or getattr(d, "paused", False) or getattr(d, "napping", False):
            return False
        self.forced = self.due = False
        wd = d.world
        side = 1 if d.x < (wd.left + wd.right) / 2 else -1  # the side with more room
        if _rng.random() < 0.4:
            x = min(max(d.x + side * 320, wd.left + 60), wd.right - 60)
            y = wd.top + 110
        else:
            x = wd.right + 70 if side > 0 else wd.left - 70
            y = wd.floor_at(min(max(x, wd.left + 1), wd.right - 1))
        self.kees = Kees(self, x, y, -side)
        self.kees.on_ground = y >= wd.floor_at(min(max(x, wd.left + 1), wd.right - 1)) - 1
        self.dropped = not self.kees.on_ground
        hp = self.tune.rival_hp
        self.dude_f, self.kees_f = Fighter(hp, hp), Fighter(hp, hp, guard=0.32)
        self.since_hit = 0.0
        self.winner = None
        self.waited = 0.0
        self.score = {"dude": 0, "kees": 0}
        self.round = 1
        self.set_phase("arrive")
        d.vx = 0.0
        d.f = 1 if self.kees.x > d.x else -1
        d.set_state(STATE, 999.0)
        return True

    def set_phase(self, p):
        self.phase, self.pt = p, 0.0

    # ---- rounds
    def won_round(self, winner):
        self.winner = winner
        self.score[winner] += 1
        self.set_phase("after")

    def match_over(self):
        return max(self.score.values()) >= max(1, int(self.tune.rival_rounds))

    def next_round(self):
        """Both back on their feet, full HP, a step apart: round N."""
        self.round += 1
        hp = self.tune.rival_hp
        for f in (self.dude_f, self.kees_f):
            f.hp = f.max_hp = hp
            f.move, f.combo, f.flinch, f.cd = None, 0, 0.0, 0.8
        self.winner = None
        self.since_hit = 0.0
        k, d = self.kees, self.d
        self.fx.append(PopText((k.x + d.x) / 2, min(k.y, d.y) - 150, f"RONDE {self.round}!"))
        self.set_phase("standoff")
        self.kees_say("round")

    # ---- the dude's half (called from Dude.think)
    def think(self, dt, cur, btn) -> bool:
        d = self.d
        if d.state == STATE:
            if self.kees is None:
                d.set_state("idle", 1.0)
                return False
            fighting = self.phase in ("arrive", "standoff", "fight")
            dist = math.hypot(cur[0] - d.x, cur[1] - (d.y - 50))
            if fighting and self.dude_f.phase == "ok" and (btn and dist < 400 or dist < 200 and self.cur_still < 0.5):
                self.pause()
                d.set_state("idle", 0.4)
                return False
            self.run_dude(dt)
            return True
        if self.kees is not None:
            if self.phase == "wait" and d.state in ("idle", "wander") and d.on_ground \
                    and self.quiet_for >= self.tune.rival_quiet_s * 0.5:
                self.resume()
                return True
            return False
        if self.can_start(dt):
            return self.start()
        return False

    def pause(self):
        self.set_phase("wait")
        self._said_wait = False
        for f in (self.dude_f, self.kees_f):
            f.move = None

    def resume(self):
        d = self.d
        self.set_phase("fight")
        d.vx = 0.0
        d.set_state(STATE, 999.0)
        if _rng.random() < 0.4:
            self.kees_say("in")

    def run_dude(self, dt):
        d, me = self.d, self.dude_f
        k = self.kees
        d.f = d.f if me.phase != "ok" else (1 if k.x >= d.x else -1)
        if self.phase in ("arrive", "standoff"):
            d.vx = 0.0
            if self.phase == "standoff" and 1.4 < self.pt < 1.5:
                d.terror.say("rival_in" if self.round == 1 else "rival_round")
            return
        if self.phase == "fight":
            self.brain(me, d, self.kees_f, k, dt, is_dude=True)
            return
        if self.phase in ("after", "leave"):
            self.settle(me, d, dt)
            return

    # ---- the rest (called from Dude.tick after his own physics)
    def step(self, dt, cur, btn):
        self.cd -= dt
        self.track_cursor(cur, dt)
        self.quiet_for = self.quiet_for + dt if self.quiet(cur, btn) else 0.0
        self.fx = [w for w in self.fx if w.step(dt)]
        if self.bubble is not None:
            if not self.bubble.step(dt):
                self.bubble = None
            elif self.kees is not None:
                self.bubble.follow(self.kees.x, self.kees.y - 125)
        k = self.kees
        if k is None:
            return
        d = self.d
        self.pt += dt
        now = d.clock()

        if k.punched:  # you hit him
            k.punched = False
            self.cursor_punch(cur)

        p = self.phase
        kf = self.kees_f
        if p == "arrive":
            k.f = 1 if d.x >= k.x else -1
            dist = abs(d.x - k.x)
            if k.on_ground and dist > 240:
                k.vx = k.f * 280.0
                kf.walk_ph += dt * 280 / 22
            else:
                k.vx = 0.0 if k.on_ground else k.vx
            if k.on_ground and self.dropped:  # dropped in from the top: a superhero landing
                self.dropped = False
                self.fx.append(PopText(k.x, k.y - 20, "BOEM!"))
                self.d.terror.sfx.play("bonk")
            if k.on_ground and (dist <= 250 or self.pt > 6.0):
                self.set_phase("standoff")
                self.kees_say("in")
        elif p == "standoff":
            k.f = 1 if d.x >= k.x else -1
            # Between rounds they can be standing on top of each other: Kees takes a few steps back.
            gap = abs(d.x - k.x)
            k.vx = -k.f * 150.0 if k.on_ground and gap < 200 and kf.phase == "ok" else 0.0
            if abs(k.vx) > 1:
                kf.walk_ph += dt * 150 / 22
            if kf.phase != "ok":
                self.settle(kf, k, dt)
            if self.pt > 2.8 and kf.phase == "ok" and self.dude_f.phase == "ok":
                self.set_phase("fight")
        elif p == "fight":
            self.since_hit += dt
            if self.since_hit > 30.0:  # nobody can get at anybody: call it off
                self.kees_say("bored")
                self.winner = None
                if d.state == STATE:
                    d.set_state("idle", 1.0)
                self.set_phase("leave")
                return
            self.brain(kf, k, self.dude_f, d, dt, is_dude=False)
            loser = "dude" if self.dude_f.hp <= 0 else "kees" if kf.hp <= 0 else None
            if loser:
                self.won_round("kees" if loser == "dude" else "dude")
        elif p == "after":
            self.settle(kf, k, dt)
            final = self.match_over()
            if 0.9 < self.pt <= 0.9 + dt * 1.5:
                if self.winner == "dude":
                    d.terror.say("rival_win" if final else "rival_round_win")
                else:
                    self.kees_say("win" if final else "round_win")
            if not final:
                if 2.0 < self.pt <= 2.0 + dt * 1.5 and self.winner == "kees":
                    d.terror.say("rival_round_lose")
                if self.pt > 3.0 and kf.phase == "ok" and self.dude_f.phase == "ok":
                    self.next_round()
                elif self.pt > 12.0:  # somebody is stuck somewhere: call the match here
                    self.finish_fight()
            elif 2.6 < self.pt <= 2.6 + dt * 1.5:
                if self.winner == "dude":
                    self.kees_say("lose")
                else:
                    d.terror.say("rival_lose")
            if final and self.pt > 3.6 and kf.phase in ("ok",):
                self.finish_fight()
        elif p == "wait":
            self.waited += dt
            kf.move = None
            if kf.phase != "ok":
                self.settle(kf, k, dt)
            else:
                dx = d.x - k.x
                k.f = 1 if dx >= 0 else -1
                gap = abs(dx)
                k.vx = k.f * 160.0 if gap > 320 else (-k.f * 120.0 if gap < 220 else 0.0)
                if abs(k.vx) > 1:
                    kf.walk_ph += dt * abs(k.vx) / 22
            if not self._said_wait and self.waited > 0.6:
                self._said_wait = True
                self.kees_say("wait")
            if self.waited > self.tune.rival_patience_s:
                self.kees_say("bored")
                self.winner = None
                self.set_phase("leave")
        elif p == "leave":
            self.settle(kf, k, dt)
            if kf.phase == "ok":
                wd = d.world
                out = 1 if k.x > (wd.left + wd.right) / 2 else -1
                limp = self.winner == "dude"
                k.f = out
                speed = 110.0 if limp else 190.0
                k.vx = out * speed
                kf.walk_ph += dt * speed / 22
                if k.x < wd.left - 80 or k.x > wd.right + 80 or self.pt > 25:
                    self.end()
                    return

        if self.kees is None:
            return
        k.physics(dt, d.world, now)
        if p in ("fight", "after") and kf.phase in ("down", "ko"):
            kf.spin += kf.spin_v * dt
            if k.on_ground:
                k.vx *= max(0.0, 1 - 7 * dt)
        k.pose = self.pose_for(kf, k, is_dude=False)
        k.place()
        k.update()

    def finish_fight(self):
        d = self.d
        save = d.life.save
        key = "rival_won" if self.winner == "dude" else "rival_lost"
        try:
            save[key] = save[key] + 1
        except KeyError:
            pass
        if d.state == STATE:
            if self.winner == "kees":
                d.set_state("stunned", 1.4)
            else:
                d.set_state("idle", 1.5)
            d.attack_cd = max(d.attack_cd, 2.0)
        self.set_phase("leave")

    def end(self):
        d = self.d
        if self.kees is not None:
            self.kees.kill()
        self.kees = None
        self.dude_f = self.kees_f = None
        if d.state == STATE:
            d.set_state("idle", 1.0)
        lo, hi = self.tune.rival_cooldown_s
        self.cd = _rng.uniform(lo, hi)
        self.phase = ""

    # ---- fighting, for either side
    def brain(self, a: Fighter, A, b: Fighter, B, dt, is_dude):
        a.cd -= dt
        a.pt += dt
        if a.phase in ("down", "ko", "getup"):
            self.settle(a, A, dt)
            return
        if a.flinch > 0:
            a.flinch -= dt
            A.vx *= max(0.0, 1 - 8 * dt)
            return
        dx = B.x - A.x
        dist, dy = abs(dx), B.y - A.y  # dy < 0: the other one is higher up
        if a.move:
            self.run_move(a, A, b, B, dt, is_dude)
            return
        A.f = 1 if dx >= 0 else -1

        # see a blow coming: maybe get the guard up
        if b.move in ("punch", "kick", "uppercut") and a.saw != b.move_id and dist < 120 and A.on_ground:
            a.saw = b.move_id
            if _rng.random() < a.guard:
                self.begin(a, "block")
                return

        # get there: walk, hop up to a ledge, drop down from one. Only ever while the other one is
        # standing still -- two of them both chasing a moving target up and down is leapfrog for ever --
        # and coming down beats going up: the one below gives the one above a moment to drop first.
        # After a while without a blow they both settle it on the floor.
        on_floor_only = self.since_hit > 12.0
        a.below = a.below + dt if dy < -45 and B.on_ground else 0.0
        if A.on_ground:
            ledge = abs(A.y - self.d.world.floor_at(min(max(A.x, self.d.world.left + 1), self.d.world.right - 1))) > 3
            if on_floor_only and ledge:
                self.drop(A, is_dude)
            elif (dy < -45 and B.on_ground and a.below > 0.7 and dist < 380 and -dy < 520
                    and not on_floor_only):
                A.vy = -min(1300.0, math.sqrt(2 * G * (-dy + 35)))
                A.vx = (A.f if dist > 8 else -A.f) * min(300.0, max(dist, 40.0) * 1.6)
                A.on_ground = False
                a.below = 0.0
                if is_dude:
                    A.plat_hwnd = None
                return
            elif dy > 45 and dist < 280 and B.on_ground:
                self.drop(A, is_dude)
            if dist > 64:
                A.vx = A.f * (250.0 if dist < 400 else 320.0)
            elif dist < 34:
                A.vx = -A.f * 130.0
            else:
                A.vx = 0.0
            if abs(A.vx) > 1:
                a.walk_ph += dt * abs(A.vx) / 22
        if a.cd > 0 or b.phase != "ok" or not A.on_ground:
            return
        if dist < 92 and abs(dy) < 60:
            r = _rng.random()
            move = "punch" if r < 0.46 else "kick" if r < 0.74 else "uppercut" if r < 0.88 else "taunt"
            self.begin(a, move)
        elif 120 < dist < 240 and abs(dy) < 40 and _rng.random() < 0.9 * dt:
            self.begin(a, "dropkick")
            A.vy, A.vx, A.on_ground = -560.0, A.f * 560.0, False
            if is_dude:
                A.plat_hwnd = None

    @staticmethod
    def begin(a, move):
        a.move, a.mt, a.hit_done = move, 0.0, False
        a.move_id += 1

    def drop(self, A, is_dude):
        if is_dude:
            if A.plat_hwnd:
                A.drop()
        else:
            A.drop_until = self.d.clock() + 0.3
            A.on_ground, A.vy = False, 60.0

    def run_move(self, a, A, b, B, dt, is_dude):
        m = MOVES[a.move]
        a.mt += dt
        k = a.mt / m["len"]
        if a.move in ("block", "taunt"):
            A.vx = 0.0
        elif a.move == "dropkick":
            if not a.hit_done and abs(B.x - A.x) < m["reach"] and abs(B.y - A.y) < 80:
                a.hit_done = True
                self.resolve(a, A, b, B, m)
                A.vx *= -0.3
            if (A.on_ground and a.mt > 0.15) or a.mt > 1.4:
                self.end_move(a, (0.5, 0.9))
            return
        else:
            A.vx = A.f * 110.0 if 0.35 < k < 0.55 else A.vx * max(0.0, 1 - 12 * dt)
            if not a.hit_done and k >= m["hit"]:
                a.hit_done = True
                self.resolve(a, A, b, B, m)
        if a.mt >= m["len"]:
            self.end_move(a, (0.3, 0.85) if a.move != "taunt" else (0.2, 0.4))

    @staticmethod
    def end_move(a, cd):
        a.move = None
        a.cd = _rng.uniform(*cd)

    def resolve(self, a, A, b, B, m):
        """The blow lands -- or meets a guard, or hits air."""
        dx = B.x - A.x
        if abs(dx) > m["reach"] or dx * A.f < -10 or abs(B.y - A.y) > 70 or b.phase != "ok":
            return  # whiff
        sfx = self.d.terror.sfx
        hx, hy = A.x + A.f * m["reach"] * 0.65, A.y - m["y"]
        self.since_hit = 0.0
        if b.move == "block" and (A.x - B.x) * B.f > 0:
            sfx.play("clang")
            self.fx.append(PopText(hx, hy, "TIK"))
            B.vx = A.f * 170.0
            a.cd += 0.3
            return
        b.move = None
        b.hp = max(0.0, b.hp - m["dmg"] * _rng.uniform(0.85, 1.15))
        b.combo += 1
        sfx.play("bonk" if _rng.random() < 0.6 else "ugh")
        self.fx.append(PopText(hx, hy, _rng.choice(WORDS)))
        if a is self.kees_f and _rng.random() < 0.25:
            self.kees_say("hit")
        if b.hp <= 0:
            self.knock(b, B, A.f, ko=True)
        elif m["down"] or b.combo >= 3:
            self.knock(b, B, A.f)
        else:
            b.flinch = 0.28
            B.vx = A.f * m["knock"]
        a.combo = 0

    def knock(self, b, B, direction, ko=False):
        b.phase, b.pt, b.move, b.combo = ("ko" if ko else "down"), 0.0, None, 0
        b.spin, b.spin_v = 0.0, direction * (11.0 if ko else 8.0)
        B.vx, B.vy = direction * (720.0 if ko else 560.0), -(820.0 if ko else 640.0)
        B.on_ground = False
        if B is self.d:
            B.plat_hwnd = None
        w = self.d.world.window_at(B.x + direction * 90, B.y - 60)
        if w is not None:  # slammed into a window: it shakes and snaps back
            self.d.shaker.shake(w.hwnd)

    def settle(self, a, A, dt):
        """Down, getting up, or out cold."""
        a.pt += dt if a.phase != "ok" else 0.0
        if a.phase in ("down", "ko"):
            if A.on_ground:
                A.vx *= max(0.0, 1 - 7 * dt)
            stay = 0.45 if a.phase == "down" else 1.9
            if A.on_ground and a.pt > stay and abs(A.vx) < 90:
                a.phase, a.pt, a.spin = "getup", 0.0, 0.0
                A.vx = 0.0
        elif a.phase == "getup":
            A.vx = 0.0
            if a.pt > 0.5:
                a.phase, a.pt, a.cd = "ok", 0.0, 0.5
        elif self.phase in ("after", "leave") and A is self.d:
            A.vx = 0.0

    def cursor_punch(self, cur):
        """You clicked Kees."""
        k, kf = self.kees, self.kees_f
        if kf is None or self.phase in ("leave",):
            return
        self.d.terror.sfx.play("bonk")
        self.fx.append(PopText(k.x, k.y - 90, "PATS!"))
        direction = 1 if k.x >= cur[0] else -1
        if kf.phase == "ok":
            kf.hp = max(1.0 if self.phase != "fight" else 0.0, kf.hp - 15)
            self.knock(kf, k, direction, ko=kf.hp <= 0)
        self.kees_say("help")
        if self.d.state == STATE or self.phase == "wait":
            self.d.terror.later(0.6, lambda: self.d.terror.say("rival_help"))
        if self.phase == "fight" and kf.hp <= 0:
            self.won_round("dude")

    # ---- talking
    def kees_say(self, cat):
        if self.kees is None:
            return
        if self.bubble is not None:
            self.bubble.kill()
        self.bubble = Bubble(_rng.choice(KEES[cat]))
        self.bubble.follow(self.kees.x, self.kees.y - 125)

    # ---- looks
    def pose_for(self, a: Fighter, A, is_dude):
        P, kit, t = self.P, self.kit, self.d.t
        if a.phase in ("down", "ko"):
            return kit["pose_ragdoll"](t, a.spin) if not A.on_ground else dataclasses.replace(
                kit["pose_ragdoll"](0.3, 0.0), spin=A.f * -1.45)
        if a.phase == "getup":
            return kit["pose_crouch"]()
        if not is_dude and self.phase == "wait":
            if abs(A.vx) > 1:
                return kit["pose_walk"](a.walk_ph, 0.45, 0.04, 0.4)
            return pose_folded(P, t)
        if self.phase in ("after", "leave"):
            won = (self.winner == "dude") == is_dude
            if self.phase == "after" and won:
                return pose_victory(P, t) if not is_dude else kit["pose_taunt"](t)
            if abs(A.vx) > 1:
                if won or self.winner is None:
                    return kit["pose_walk"](a.walk_ph, 0.55, 0.08, 0.5)
                return kit["pose_walk"](a.walk_ph, 0.28, 0.32, 0.2)  # limping off
            return kit["pose_dizzy"](t) if not won and self.winner else kit["pose_stand"](t)
        if self.phase == "arrive":
            if not A.on_ground:
                return kit["pose_air"](A.vy, t)
            if abs(A.vx) > 1:
                return kit["pose_walk"](a.walk_ph, 0.85, 0.25, 1.3)
            return pose_guard(P, t)
        if self.phase == "standoff":
            if is_dude:
                return kit["pose_taunt"](t)
            if abs(A.vx) > 1:
                return kit["pose_walk"](a.walk_ph, 0.45, 0.04, 0.4)
            return pose_guard(P, t)
        if a.flinch > 0:
            return pose_flinch(P)
        m = a.move
        if m == "punch":
            return kit["pose_punch"](a.mt / MOVES["punch"]["len"])
        if m == "kick":
            return kit["pose_kick"](a.mt / MOVES["kick"]["len"])
        if m == "uppercut":
            return pose_uppercut(P, a.mt / MOVES["uppercut"]["len"])
        if m == "dropkick":
            return pose_dropkick(P)
        if m == "block":
            return pose_block(P)
        if m == "taunt":
            return kit["pose_taunt"](t)
        if not A.on_ground:
            return kit["pose_air"](A.vy, t)
        if abs(A.vx) > 5:
            p = kit["pose_walk"](a.walk_ph, 0.55, 0.12, 0.5)
            g = pose_guard(P, t)
            return dataclasses.replace(p, upper=g.upper, lower=g.lower)
        return pose_guard(P, t)

    def pose(self):
        """The dude's pose while he's in the fight."""
        d = self.d
        if d.state != STATE or self.dude_f is None:
            return None
        return self.pose_for(self.dude_f, d, is_dude=True)

    def paint(self, qp, ox, oy, pose, f):
        d = self.d
        if d.state != STATE or self.dude_f is None:
            return
        hx, hy = self.kit["skeleton"](pose, f)["head"]
        if self.phase in ("fight", "standoff", "after"):
            self.paint_hp(qp, ox, oy + hy - 34, self.dude_f, self.score["dude"], self.tune.rival_rounds)
        if self.dude_f.phase == "ko" or (self.phase == "after" and self.winner == "kees"):
            self.paint_stars(qp, ox + hx, oy + hy)

    @staticmethod
    def paint_hp(qp, cx, y, fighter, wins=0, need=0):
        w, h = 54.0, 7.0
        need = int(need)
        if need > 1:  # rounds won, as pips under the bar
            for i in range(need):
                px = cx + (i - (need - 1) / 2) * 11
                qp.setPen(QPen(QColor(255, 255, 255, 200), 1.5))
                qp.setBrush(QColor(255, 200, 40) if i < wins else QColor(20, 20, 24, 160))
                qp.drawEllipse(QPointF(px, y + h + 6), 3.5, 3.5)
        k = max(0.0, min(1.0, fighter.hp / fighter.max_hp))
        qp.setPen(QPen(QColor(255, 255, 255, 200), 2))
        qp.setBrush(QColor(20, 20, 24, 200))
        qp.drawRoundedRect(QRectF(cx - w / 2, y, w, h), 3, 3)
        qp.setPen(Qt.NoPen)
        col = QColor(70, 200, 90) if k > 0.5 else QColor(240, 190, 40) if k > 0.25 else QColor(225, 50, 40)
        qp.setBrush(col)
        qp.drawRoundedRect(QRectF(cx - w / 2 + 1.5, y + 1.5, (w - 3) * k, h - 3), 2, 2)
        qp.setBrush(Qt.NoBrush)

    def paint_stars(self, qp, hx, hy):
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(255, 210, 40))
        for i in range(3):
            ang = self.d.t * 6 + i * math.tau / 3
            qp.drawEllipse(QPointF(hx + math.cos(ang) * 16, hy - 14 + math.sin(ang) * 5), 3, 3)
        qp.setBrush(Qt.NoBrush)

    # ---- housekeeping
    def set_visible(self, vis):
        for w in [self.kees, self.bubble, *self.fx]:
            if w is not None:
                w.setVisible(vis)

    def release(self):
        for w in [self.kees, self.bubble, *self.fx]:
            if w is not None:
                w.kill()
        self.kees, self.bubble, self.fx = None, None, []
        self.dude_f = self.kees_f = None
        self.phase = ""
        if self.d.state == STATE:
            self.d.set_state("idle", 1.0)
