# DCS Missions

A hangar of ready-to-fly DCS World missions, each with a full story, an interactive briefing, a slide deck, and kneeboard pages.

| Mission | Aircraft | Story device |
| --- | --- | --- |
| Operation BROKEN SPAN | F/A-18C | Classic strike, but the SA-6 intel is 36 hours old |
| Operation SILENT ORCHARD | F-16C | The hunt: the SA-11 is at one of two hides, chosen at random |
| Operation HOLD FAST | A-10C II | The ticking clock: the attack comes down one of two roads, and the ending branches |
| Operation BLUE WATER | F-14B, from the carrier | Fleet defense at dusk: the raid's axis is random, the big tanker may go home early, and you recover aboard at last light |
| Operation DEEP CUT | AV-8B | The back door: tanker, then terrain-following through mountain valleys, a pop-up attack, and recovery at a different field |
| Operation LIFELINE | F/A-18C, alert scramble | Rescue cover: stop the search party before it reaches a downed pilot, then escort the rescue helicopter in and out |
| Operation GREY HULL | F/A-18C, from the carrier | Deception: two radar contacts, one of them warships. The intel on which one can be wrong; Harpoons from low level |

Every briefing and deck now includes an **altitude profile** alongside the map. Dashed legs are flown above ground level, so you can see how differently each mission flies.

## Two audiences: pilots and the director

Real briefings don't know what's going to happen, and ours shouldn't either. Each mission renders two kinds of output:

- **For pilots:** `briefing.html`, `slides.html` and the kneeboard. These hold the plan and the intel at brief time. Every threat is marked **confirmed**, **suspected** or **possible**, and may be stale or wrong. They contain no trigger scripts, no hidden units and no outcomes.
- **For the director:** `director.html` (**spoilers**). It shows what's really in the mission: briefed intel next to ground truth, every random roll and its odds, the full trigger script with radio calls, and the debrief outcomes. It's for whoever builds, runs or debriefs the mission.

Missions also use randomness inside DCS, so even the director doesn't know exactly how a flight will go: a SAM can be in one of several places, a threat can have a set chance to appear at all, and an attack can come from different directions. A test fails the build if anything from the director's side leaks into a pilot-facing page.

The `.miz` itself necessarily contains the truth. Pilots who want surprises shouldn't open it in the Mission Editor.

## Fly a mission (no install needed)

Everything in [`hangar/`](hangar/) is already rendered:

1. Open [`hangar/README.md`](hangar/README.md) to browse the missions.
2. Download the mission's `.miz` and put it in `Saved Games/DCS/Missions/`.
3. Download its `briefing.html` and open it in a browser for the story, the plan on a map, and the briefing cards. GitHub shows HTML files as source code, so download it rather than viewing it on GitHub.
4. To brief your squadron, download `slides.html` and present it (see below).
5. The kneeboard pages are already inside the `.miz`. The PNGs are in the repo too, if you want to print them.
6. After the flight, whoever ran it opens `director.html` to see what was really there and read the matching outcome.

## Present the slide deck

`slides.html` tells the mission as a story, one idea per slide: the hook, the backstory, the cast, the battlespace, the target and threat intel, then one slide per storyboard phase with the plan and a map of that leg. It ends at "Questions?". Debrief outcomes are in `director.html`, so the deck is safe to share before the flight.

| Key | Action |
| --- | --- |
| → / Space / click right side | Next slide |
| ← / click left side | Previous slide |
| N | Presenter notes |
| F | Fullscreen |
| Home / End | First / last slide |

The maps are drawn offline, so the deck works without internet (fonts fall back if offline). To get a PDF, print from Chrome with "Background graphics" on: each slide becomes one page.

## How the repo works

```
missions/<id>/mission.yaml   source of truth: story, units, route, triggers, briefing
dcsmb/                       the builder (Python)
templates/                   briefing, kneeboard and hangar page layouts
hangar/<id>/                 rendered output: <id>.miz, briefing.html, slides.html, director.html, kneeboard/*.png
scripts/fetch_coastline.py   one-off: coastline data for the slide maps (re-run for a new theater)
hangar/index.html, README.md hangar listing, regenerated on every build
```

The `.miz`, briefing, slide deck, and kneeboard all come from the same `mission.yaml`, so they can't disagree. **Don't edit files in `hangar/` by hand.** They're overwritten on the next build. That includes saving a `.miz` from the DCS Mission Editor: carry the change back into `mission.yaml` instead.

The hangar is always committed fully rendered. Builds are reproducible: rebuilding an unchanged mission produces byte-identical files, so only missions that actually changed show up in a commit.

## Modify or add a mission

### 1. Set up (once)

You need Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m playwright install chromium   # renders the kneeboard PNGs
```

### 2. Edit

Change `missions/<id>/mission.yaml`, or copy an existing mission folder to start a new one (change `meta.id` to match the folder name).

| Section | What it controls |
| --- | --- |
The **Seen by** column says which audience gets each section.

| Section | Seen by | What it controls |
| --- | --- | --- |
| `meta` | everyone | Title, map, date, start time, weather, `role` (mission type, e.g. Strike, SEAD, CAS, RESCAP, Anti-ship: the hangar filters on it) |
| `narrative` | pilots, except `outcomes` (director) | Backstory, cast, opening quote. The backstory also becomes the in-game briefing text. |
| `situation`, `objectives`, `roe`, `comms` | pilots | Briefing cards, kneeboard pages, in-game task text |
| `threats` | pilots | **Intel, not truth.** `intel: confirmed / suspected / possible`, optional `area_km` for position uncertainty. Can be wrong on purpose. |
| `flights` | pilots | The player flight: aircraft, `base`/`land` (an airfield or a ship group name), loadout by pylon, waypoints (`action: bomb / sead / cas / cap / antiship`; `agl: true` for terrain-following legs). A waypoint with `zone_km` gets a trigger zone. |
| `ships` | friendly: pilots; red: director | Ship groups (first type is the lead, e.g. `Stennis`), `route` and `speed_kts`, `tacan`, `icls`, ATC `freq_mhz`, `late_activation` |
| `zones` | director | Extra named trigger zones (e.g. a missile launch line). Usable anywhere a waypoint name is. |
| `target` | pilots (position, description) | `area_km` for an estimated position. What counts as destroyed: `zone_m` (scenery in the zone dies) and/or `groups`, with `kill_pct` (default 100). |
| `units` | director | **Ground truth.** Ground groups, optional `route` and `speed_kmh` for moving units. `late_activation` groups wait for a trigger or variant. |
| `support` | friendly: pilots; red: director | `awacs`, `tanker` (with `tacan`), `cap`, `intercept` (scrambles from an airfield), `flight` (spawns in the air and flies a `route`: raids, sweeps, or a helicopter with `task: transport`; route points take `agl: true` and, for helicopters, `land_s` to set down for that many seconds) |
| `variants` | director | Random choices rolled at mission start. Each option can `activate` groups, send a `message`, and wait for a `when`. |
| `storyboard` | `brief` and `notes`: pilots; `script` and `trigger`: director | Ordered phases. `brief` is what pilots are told; `script` is what really happens; `trigger` / `triggers` become DCS trigger rules. |

A trigger's `when` holds one or more conditions, all of which must be true:

- `time_after` (seconds)
- `player_in_zone` (waypoint or zone name; watches your aircraft, not the wingman)
- `group_dead` (group name)
- `group_life_below: [group, percent]` (damaged: e.g. 95 means "anything hit")
- `group_in_zone: [group, zone]`
- `flag` / `flag_false` (number)
- `target_destroyed`
- `variant: [name, option]`

`comms` entries take `radio` and `channel` to land on a cockpit preset. Radio 1 channel 1 is always the flight frequency. Leave them off for scripted-only voices, which appear as on-screen text and don't answer the radio menu.

Add `chance: 1-99` to roll the trigger once at mission start; if the roll misses, the trigger never fires. Actions are `activate`, `deactivate`, `message` (+ `seconds`) and `set_flag`.

Unit and weapon names are pydcs names. Weapons are the attribute names on `dcs.planes.<Aircraft>.Pylon<N>`, e.g. `dcs.planes.FA_18C_hornet.Pylon2`. The build stops with a clear message if a name, waypoint, or group reference is wrong.

### 3. Build and commit

```bash
.venv/bin/python -m dcsmb build      # rebuilds every mission and the hangar index
.venv/bin/python -m pytest -q tests  # optional sanity checks
git add missions hangar && git commit
```

Always commit the YAML change and the rebuilt `hangar/` together. `--no-kneeboard` skips Chromium if you only want a quick check of the `.miz` and briefing, but don't commit a build made that way (it drops the kneeboard pages).

### 4. Check in DCS

DCS doesn't run on the build machine, so after changing positions or triggers, open the `.miz` in the Mission Editor and fly it once. Check that:

- target zones sit on the target (map coordinates come from OpenStreetMap; DCS scenery can be tens of metres off);
- ground units are on sensible terrain;
- radio calls and activations fire when expected;
- random variants really vary: restart the mission a few times and confirm `director.html`'s options all show up.
