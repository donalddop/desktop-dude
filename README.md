# desktop-dude

A stick figure that lives on your desktop and fights your cursor. Windows only.

    uv run --gui-script desktop_dude.py     # or double-click run.cmd

## Install

Windows 10/11. Download **DesktopDude-setup.exe** from the
[latest release](https://github.com/donalddop/desktop-dude/releases/latest) and run it (per-user install, no admin
rights). It's not code-signed, so Windows SmartScreen asks once: *More info* > *Run anyway*.
Prefer portable? Unzip **DesktopDude-standalone.zip** and start `DesktopDude.exe`.
The installed exe updates itself: every 6 hours it checks GitHub for a new release, verifies the download's
SHA-256, installs it silently and restarts (tray > Auto-update to switch it off, tray > Check for updates to
check now). The portable zip only tells you a new version is out.
The exe keeps its save game, log, sounds and config (`dude_config.json`, `ha.json`) in `%LOCALAPPDATA%\DesktopDude`.

### From source

Needs [uv](https://docs.astral.sh/uv/getting-started/installation/):

    winget install astral-sh.uv
    git clone https://github.com/donalddop/desktop-dude
    cd desktop-dude
    uv run --gui-script desktop_dude.py

uv installs Python and the dependencies on the first run. Build the exe + installer yourself with `.\\build.ps1`. Sound effects are off by default (tray > Sound).
He speaks Amsterdam street Dutch and swears a lot. You've been warned.

## What he does

- click him: punch. drag + release: throw.
- he grabs your cursor: shake the mouse hard, or just click him.
- Ctrl+Alt+P pause, Ctrl+Alt+Q quit (also in the tray icon).
- naps while a fullscreen app has focus.
- angry + cursor out of reach: bazooka. Red laser = dodge time.
- katana: dash-slash, cuts windows (they slide and snap back), parries your clicks.
- climbs windows and screen edges, double jumps, roams the whole screen.
- total war when he's furious: drones (click them down), a tank (click it 3x), airstrikes.
  Ctrl+Alt+W enrages him on demand; tray menu has a war mode on/off switch.
- defend yourself: Ctrl+Alt+M drops a landmine under your cursor (2 wreck a tank),
  Ctrl+Alt+F places anti-air flak that shoots down drones and the bomber.
- desktop terror, also when he's just bored: glass break, earthquake, power cut, graffiti
  (sticks until you click it), icon kidnapping, window surfing, fake errors, cuttlefish hunting,
  speech bubbles and sound (off by default, tray > Sound turns it on). Ctrl+Alt+T or the tray's 'Terror test' menu triggers it on demand.
  Cuttlefish hunt: the first hit kills one. A drawn dead cuttlefish drops, he eats it bite by bite
  and burps. The real fish in CuttlefishPet are never touched.
- all damage is temporary; he never clicks, types or touches files,
  and never moves the cursor while you hold a mouse button.

Tests: `uv run --group dev pytest`. Pose sheet: `uv run desktop_dude.py --poses`.

## Arsenal (Ctrl+Alt+A)

When he's chasing you he grabs a random weapon (more serious stuff the angrier he gets). Tray > Weapon test lets you pick one.

- Melee: baseball bat (home run), golf club (FORE!, sends your cursor flying), frying pan, raw herring, chainsaw (cuts windows, they snap back), rubber chicken
- Guns: pistol, machine gun, shotgun, sniper (red laser dot on your cursor first)
- Thrown: grenade (bounces, 2s fuse), dynamite (3-2-1, big boom + quake), cream pie (splats on screen, fades), boomerang (hits you on the way out and back)

Same rules: cursor is never flung while you hold a mouse button, windows snap back, holes and splats fade. Punch or throw him and he drops it.

## His life (life.py)

- **Your apps:** watching something (YouTube, Netflix, VLC...)? He sits down with popcorn. Coding or in Claude?
  "Werk je wel, mattie?". Only the active window's title is read.
- **Your music:** reads Windows' output peak meter (nothing is recorded) and dances on the beat: headbang,
  hands up, running man, DJ scratch with headphones.
- **Day/night:** at night he wears a nightcap and falls asleep. Wake him up and he's furious. Mornings: coffee first.
- **Grudge & levels:** `dude_save.json` remembers punches, throws, hits and duels across restarts. Grudge makes
  him angrier (and he'll challenge you to a duel). XP unlocks weapons: bat/pan/chicken/pie/herring first,
  then golf/boomerang/pistol, shotgun/grenade/MG, and finally chainsaw/sniper/dynamite.
- **Recycle Bin:** throw him onto your Recycle Bin icon. He rattles around in it and climbs out sooty and livid.
- **Duel (Ctrl+Alt+D):** HP bars for you and him, best of 3. Your punches/throws hurt him, his hits on your
  cursor hurt you. Run away for 20s and you forfeit.
- **Taskbar:** he sits on your clock swinging his legs, or kicks the Start button (animation only, no clicks).
- **Weather:** real weather for your location (Open-Meteo, no key; set it in `dude_config.json`:
  `{"lat": 52.37, "lon": 4.90}`, default Amsterdam). Rain/snow/thunder showers over your screen now and
  then, umbrella up; with snow he builds a snowman that melts.
- **Mini-dudes:** really angry? He calls in 3 mini-dudes that slap your cursor. Click them: POEF.
- **Home Assistant (optional):** put `ha.json` next to the script:
  `{"url": "http://homeassistant.local:8123", "token": "<long-lived access token>"}` (gitignored).
  The "power cut" terror then snapshots the lights that are on, switches them off and restores the snapshot ~2s later.

- **Cuttlefish Pet:** if [Cuttlefish Pet](https://github.com/donalddop/cuttlefish-pet) (2.9+) runs too, they talk
  over its link pipe. The dude rides a cuttlefish (cowboy hat on) until it bucks him off, carries one overhead
  and throws it, pets one (hearts), fights one (it inks him back) and, rarely, eats one for real: it lands in
  Cuttlefish Pet's graveyard as *opgegeten door de dude*. Cuttlefish Pet refuses that with two or fewer left.
  Tray > Aquarium triggers each on demand.

Tray > Life test triggers everything on demand; the tray also shows level, XP, grudge and Home Assistant status.
