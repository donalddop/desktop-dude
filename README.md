# desktop-dude

A stick figure that lives on your desktop and fights your cursor. Windows and macOS.

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

### macOS

macOS 13 or newer, Apple Silicon or Intel. From the
[latest release](https://github.com/donalddop/desktop-dude/releases/latest) download
**DesktopDude-macos-arm64.zip** (M1/M2/M3/M4) or **DesktopDude-macos-x86_64.zip** (Intel), unzip it and drag
**DesktopDude.app** into Applications.

- It isn't notarized by Apple (that needs a paid developer account), so macOS blocks it the first time:
  - **macOS 15 Sequoia and newer:** open it once (it gets blocked), then System Settings > Privacy & Security,
    scroll down to *"DesktopDude" was blocked* > **Open Anyway**. (Right-click > Open no longer works there.)
  - **macOS 13-14:** right-click the app > Open > Open.
  - Says it's "damaged" or still refuses? Run once in Terminal:
    `xattr -dr com.apple.quarantine /Applications/DesktopDude.app`
- He lives in the menu bar (no Dock icon). The menu bar icon has everything the Windows tray has.
- To shake and surf your windows he needs **Accessibility**: macOS asks the first time (System Settings > Privacy &
  Security > Accessibility > DesktopDude on). Without it he leaves your windows alone; everything else works.
  The app is only ad-hoc signed, so after installing a new version macOS forgets that: switch it off and on again
  (or remove it with **-** and let him ask again).
- The Ctrl+Option hotkeys may need **Input Monitoring** (same settings page). The menu bar icon does it all too.
- Not on the Mac: dancing to your music and commenting on videos (macOS doesn't let apps hear the system sound),
  icon football, and Cuttlefish Pet (a Windows app). No auto-update yet: the menu has *Check for updates*.
- Save game, log and config live in `~/Library/Application Support/DesktopDude`.

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

**Tuning (how often and how hard he goes off):** every number for rage thresholds, how fast rage cools down and how much a punch/throw/parry adds, terror frequency and
cooldowns, the odds per terror act, and when drones/tank/airstrike come lives in `tuning.py`. Override any of
them in a `"tuning"` block in `dude_config.json`, e.g. `{"tuning": {"terror_every_calm_s": 90, "rage_tank": 0.75,
"terror_weights": {"popup": 0.5}}}`, then tray > Reload tuning (no restart needed). Typos are skipped and logged in `desktop_dude.log`.

<details>
<summary>All tuning keys with their defaults</summary>

<!-- tuning-table:start (generated by tools/tuning_table.py --write, do not edit by hand) -->

**Rage thresholds (rage runs 0..1)**

| Key | Default | What it does |
| --- | --- | --- |
| `rage_angry` | 0.4 | from here terror gets angry: more often, plus glass and quake |
| `rage_blackout` | 0.7 | from here a blackout (power cut) is possible |
| `rage_drones` | 0.45 | war: drones |
| `rage_drones_three` | 0.8 | war: three drones instead of two |
| `rage_tank` | 0.65 | war: tank |
| `rage_air` | 0.85 | war: airstrike |

**Rage: how fast he cools down and how much each hit adds (desktop_dude.py)**

| Key | Default | What it does |
| --- | --- | --- |
| `rage_cooldown_per_s` | 0.012 | rage drops this much per second |
| `rage_punch` | 0.12 | you punch him |
| `rage_throw` | 0.15 | you throw him |
| `rage_throw_speed_bonus` | 0.2 | plus up to this much for a full-speed throw (goes with `rage_throw`) |
| `rage_parry` | 0.05 | he blocks your punch with the katana |
| `rage_rocket_jump` | 0.1 | his own rocket blows up next to him |

**How rage drives his moves (desktop_dude.py): value = base + per_rage x rage, cooldowns floored**

| Key | Default | What it does |
| --- | --- | --- |
| `chase_speed` | 250 | px/s running after your cursor |
| `chase_speed_per_rage` | 150 | plus this much at full rage (goes with `chase_speed`) |
| `climb_speed` | 240 | px/s up a window edge |
| `climb_speed_per_rage` | 140 | plus this much at full rage (goes with `climb_speed`) |
| `katana_cooldown_s` | 4.5 | wait between katana slashes |
| `katana_cooldown_per_rage` | 3 | minus this much at full rage (goes with `katana_cooldown_s`) |
| `katana_cooldown_min_s` | 1.5 | but never shorter than this (goes with `katana_cooldown_s`) |
| `bazooka_cooldown_s` | 8 | wait between bazooka shots |
| `bazooka_cooldown_per_rage` | 4 | minus this much at full rage (goes with `bazooka_cooldown_s`) |
| `bazooka_cooldown_min_s` | 3 | but never shorter than this (goes with `bazooka_cooldown_s`) |
| `slash_push` | 160 | px a katana hit shoves your cursor |
| `slash_push_per_rage` | 140 | plus this much at full rage (goes with `slash_push`) |
| `grab_chance` | 0.3 | chance he grabs your cursor when in reach |
| `grab_chance_per_rage` | 0.3 | plus this much at full rage (goes with `grab_chance`) |
| `rocket_speed` | 900 | px/s of a bazooka rocket |
| `rocket_speed_per_rage` | 400 | plus this much at full rage (goes with `rocket_speed`) |
| `rage_katana` | 0.2 | from this rage he slashes with the katana |
| `rage_bazooka` | 0.3 | from this rage he pulls the bazooka |
| `rage_chase_after_taunt` | 0.3 | after a taunt he runs after you (instead of idling) above this rage |
| `rage_getup_notice` | 0.35 | getting up after a throw: above this rage he spots you ('!') |
| `rage_kick` | 0.3 | from this rage he kicks the window he stands on / bumps into |
| `kick_chance_per_rage_s` | 0.3 | with this chance per second x rage (goes with `rage_kick`) |
| `rage_window_katana` | 0.5 | above this rage a window attack may be a katana slash, not a kick |
| `window_katana_chance` | 0.5 | with this chance (when the katana is ready) (goes with `rage_window_katana`) |
| `rage_parry_anytime` | 0.3 | from this rage he can parry your punch outside a slash |
| `parry_chance` | 0.35 | with this chance (mid-slash he always parries) (goes with `rage_parry_anytime`) |
| `attack_pause_s` | 2.8 | pause after a kick/slash on a window |
| `attack_pause_per_rage` | 1.8 | minus this much at full rage (goes with `attack_pause_s`) |
| `attack_pause_min_s` | 0.8 | but never shorter than this (goes with `attack_pause_s`) |
| `punch_push` | 90 | px his punch shoves your cursor |
| `punch_push_per_rage` | 120 | plus this much at full rage (goes with `punch_push`) |
| `crack_chance` | 0.4 | chance a punch on your cursor cracks the screen |
| `crack_chance_per_rage` | 0.6 | plus this much at full rage (goes with `crack_chance`) |
| `notice_per_s` | 0.2 | chance per second he notices you within reach (450 px) |
| `notice_per_s_per_rage` | 1.3 | plus this much at full rage (goes with `notice_per_s`) |
| `bazooka_fire_per_s` | 0.15 | chance per second he fires the bazooka when in range |
| `bazooka_fire_per_s_per_rage` | 0.6 | plus this much at full rage (goes with `bazooka_fire_per_s`) |
| `after_attack_chase_per_rage` | 1 | chance to keep chasing you after an attack = this x rage |
| `after_attack_chase_s` | 5 | how long that chase lasts |
| `after_attack_rest_min_s` | 1 | otherwise he idles between this |
| `after_attack_rest_max_s` | 2 | and this many seconds (goes with `after_attack_rest_min_s`) |

**Terror: how often (on average one act per N seconds while idle) and the pause after one**

| Key | Default | What it does |
| --- | --- | --- |
| `terror_first_delay_s` | 25 | seconds before his very first terror act |
| `terror_every_calm_s` | 45 | one act per this many seconds on average while calm |
| `terror_every_angry_s` | 12 | one act per this many seconds on average while angry |
| `terror_cooldown_calm_s` | [30, 60] | pause [min, max] after an act while calm |
| `terror_cooldown_angry_s` | [10, 20] | pause [min, max] after an act while angry |
| `blackout_cooldown_s` | 120 | at least this long between two blackouts |
| `terror_weights` | graffiti 3, popup 1.5, taunt 1, steal 2, surf 2.5, hunt 2, glass 2.5, quake 1.5, blackout 1.2 | relative odds per act |

**War: chance per second once rage is high enough, and the wait before the next one**

| Key | Default | What it does |
| --- | --- | --- |
| `drones_rate` | 0.5 | drones: chance per second once rage passes rage_drones |
| `tank_rate` | 0.35 | tank: chance per second once rage passes rage_tank |
| `air_rate` | 0.35 | airstrike: chance per second once rage passes rage_air |
| `drones_first_s` | 6 | no drones in the first this-many seconds after start |
| `tank_first_s` | 12 | no tank in the first this-many seconds after start |
| `air_first_s` | 20 | no airstrike in the first this-many seconds after start |
| `drones_cooldown_s` | 45 | wait before drones can come again |
| `tank_cooldown_s` | 75 | wait before a tank can come again |
| `air_cooldown_s` | 60 | wait before an airstrike can come again |

<!-- tuning-table:end -->

Rage runs 0..1; a `*_per_rage` key is the full-rage amount on top of (or off) its base key. Changed something in `tuning.py`? Run
`uv run python tools/tuning_table.py --write`; a test fails while this table and `tuning.py` disagree.

</details>

## Arsenal (Ctrl+Alt+A)

When he's chasing you he grabs a random weapon (more serious stuff the angrier he gets). Tray > Weapon test lets you pick one.

- Melee: baseball bat (home run), golf club (FORE!, sends your cursor flying), frying pan, raw herring, chainsaw (cuts windows, they snap back), rubber chicken
- Guns: pistol, machine gun, shotgun, sniper (red laser dot on your cursor first)
- Thrown: grenade (bounces, 2s fuse), dynamite (3-2-1, big boom + quake), cream pie (splats on screen, fades), boomerang (hits you on the way out and back)

Same rules: cursor is never flung while you hold a mouse button, windows snap back, holes and splats fade. Punch or throw him and he drops it.

## Your bare desktop (vandal.py, graffiti.py)

When he can see bare wallpaper (no windows in the way) he gets creative, on the wallpaper layer itself: behind
your icons and under every window, like it's really on the wall (the Wallpaper Engine trick: a window parented
to the WorkerW behind the desktop icons). All of it is temporary and owned by the dude: Tray > Clear graffiti,
or quit him, and your desktop is back. Your real wallpaper file and icon layout are never touched.

- **Graffiti on your wallpaper:** tags, throw-ups and pieces in a Mokum style: bubble letters with a fat outline,
  3D drop, chrome / Ajax-red / toxic / oranje palettes, drips, shine, crowns, XXX crosses and a signature.
  Words like MOKUM, 020, BOEF, SKEER, *los mokumos*, *grand theft fiets*. Fades after 20 minutes. No bare
  wallpaper in sight? Then he sprays on top of the screen, high up and out of the way of where you type
  (click a tag to wipe it).
- **A hole in the wall:** he punches through your wallpaper: bricks behind it, cracks, and a Mokum rat peeking
  out. After a bit he tapes it up (*niemand merkt het*) and it fades.
- **Icon football:** he kicks a copy of one of your icons around the bottom of the screen, then scores it back
  home. The real icon hides under a patch of your own wallpaper meanwhile. Swipe your cursor through the ball
  or click it to steal it from him.

Tray > Desktop vandalism triggers each on demand. Fonts: Sedgwick Ave Display, Rubik Bubbles (OFL) and Permanent
Marker (Apache 2.0) from Google Fonts, licenses in `assets/fonts`.

## His life (life.py)

- **Your apps:** watching something (YouTube, Netflix, VLC...)? He sits down with popcorn. Coding or in Claude?
  "Werk je wel, mattie?". Only the active window's title is read.
- **Your music:** reads Windows' output peak meter and dances on the beat: headbang, hands up, running man,
  DJ scratch with headphones. He can tell music from people talking (ears.py): a podcast or a video is loud
  too, but he won't dance to it. Music has a periodic beat, speech has voice activity (Silero VAD); a vote
  over the last ~18 s decides.
- **Comments on what you watch (opt-in, Tray > Comment on videos/podcasts):** when people talk he listens to
  ~20 s, a local [Whisper](https://github.com/SYSTRAN/faster-whisper) (small, CPU) writes it down and a local
  [Ollama](https://ollama.com) model makes one cheeky line of it, in a speech bubble, every minute or two.
  Everything stays on your PC: audio lives in memory only, nothing is saved or sent anywhere, and nothing is
  transcribed while a call app (Teams, Discord, Zoom, ...) is playing sound. Needs Ollama with a chat model
  (it picks one that's already loaded, else gemma/qwen/llama; force one with `"listen_model"` in
  `dude_config.json`). The first time it downloads the Whisper model (~480 MB) to `%LOCALAPPDATA%\DesktopDude\models`.
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
