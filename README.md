# DCS Missions

Ready-to-fly DCS World missions and campaigns on the Caucasus map. Each one comes with a full story, an interactive briefing, a slide deck and kneeboard pages.

## Fly the missions

1. Click **Code → Download ZIP** on GitHub (or clone the repo) and unzip it anywhere.
2. Double-click **`Mission Hangar.html`** in the top folder. It opens the hangar in your browser: every campaign and mission, with its briefing, slide deck, kneeboard and `.miz` download. Maps and fonts load from the internet; everything else works offline.
3. Install in DCS:
   - **A single mission:** copy its `.miz` from `hangar/<mission>/` into `Saved Games/DCS/Missions/` and open it from the **Mission** menu.
   - **A campaign:** copy its whole folder from `hangar/campaigns/` into `Saved Games/DCS/Missions/Campaigns/` and pick it from the **Campaign** menu. Passing a chapter unlocks the next.
4. The kneeboard pages are already inside each `.miz`.

Pilots: briefings, decks and kneeboards only hold what your squadron knows at brief time. The **director** pages are spoilers, for whoever runs or debriefs the flight.

## What's in the hangar

### Black Sea operations

| Mission | Aircraft | Story device |
| --- | --- | --- |
| Operation BROKEN SPAN | F/A-18C | Classic strike, but the SA-6 intel is 36 hours old |
| Operation SILENT ORCHARD | F-16C | The hunt: the SA-11 is at one of two hides, chosen at random |
| Operation HOLD FAST | A-10C II | The ticking clock: the attack comes down one of two roads, and the ending branches |
| Operation BLUE WATER | F-14B, from the carrier | Fleet defense at dusk: the raid's axis is random, the big tanker may go home early, and you recover aboard at last light |
| Operation DEEP CUT | AV-8B | The back door: tanker, then terrain-following through mountain valleys, a pop-up attack, and recovery at a different field |
| Operation LIFELINE | F/A-18C, alert scramble | Rescue cover: stop the search party before it reaches a downed pilot, then escort the rescue helicopter in and out |
| Operation GREY HULL | F/A-18C, from the carrier | Deception: two radar contacts, one of them warships. The intel on which one can be wrong; Harpoons from low level |

### Training events

Training missions are syllabus events, briefed like a real training sortie: training rules, knock-it-off, special subjects, a grade sheet and debrief focus. Nothing is hidden or random. The aggressors and range targets are on the briefing map exactly as they'll fly.

| Event | Aircraft | What's trained |
| --- | --- | --- |
| LONG VALLEY | 2× F/A-18C, Kutaisi | Air refuelling, then a timed low-level route (the sim calls each checkpoint EARLY / ON TIME / LATE) |
| GAREJA RANGE | F/A-18C, Vaziani | Weapons qualification: GBU-12, Mk-82 CCIP and strafe, cleared in order by range control (fouls are called) |
| RED AIR | F/A-18C, Kobuleti | A BVR intercept on a MiG-29, then 1v1 and 1v2 BFM with F-5Es, with a hard deck the sim calls |

### Campaigns

Four campaigns, 20 F/A-18C missions, each a story flown in order. Every campaign has a page in the hangar and installs into DCS as a real campaign (a `.cmp` and its numbered `.miz` files).

| Campaign | Chapters | Setting | Arc |
| --- | --- | --- | --- |
| WORK-UPS (training) | 5 | Jan 2038, Kutaisi, Vaziani, Senaki and the Stennis | Day and night carrier quals, SEAD against live emitters, CAS with a JTAC, and a graduation checkride |
| IRON GATE | 5 | Apr 2038, Liakhvi valley | An armoured brigade comes through the Roki tunnel: armed recce, the Transcam bridges, the SA-11, holding Gori, and the supply dump at Java |
| HIGH TIDE | 5 | May 2038, from the Stennis | A landing force at Ochamchire: photo recce, night minelayers off Poti, blinding an SA-10 with decoys, the back-door strike, and stopping the landing |
| DARK HORSE | 5 | Jun 2038, night and weather | Mobile Scuds firing at Kutaisi: the hunt, the depot under a low ceiling, the radar on the ridge, JDAMs on coordinates passed in flight, and the headquarters |

The whole timeline is set in 2038: training in January and February, the Black Sea missions in March, then IRON GATE, HIGH TIDE and DARK HORSE.

Every briefing and deck now includes an **altitude profile** alongside the map. Dashed legs are flown above ground level, so you can see how differently each mission flies.

## Two audiences: pilots and the director

Real briefings don't know what's going to happen, and ours shouldn't either. Each mission renders two kinds of output:

- **For pilots:** `briefing.html`, `slides.html` and the kneeboard. These hold the plan and the intel at brief time. Every threat is marked **confirmed**, **suspected** or **possible**, and may be stale or wrong. They contain no trigger scripts, no hidden units and no outcomes.
- **For the director:** `director.html` (**spoilers**). It shows what's really in the mission: briefed intel next to ground truth, every random roll and its odds, the full trigger script with radio calls, and the debrief outcomes. It's for whoever builds, runs or debriefs the mission.

Missions also use randomness inside DCS, so even the director doesn't know exactly how a flight will go: a SAM can be in one of several places, a threat can have a set chance to appear at all, and an attack can come from different directions. A test fails the build if anything from the director's side leaks into a pilot-facing page.

The `.miz` itself necessarily contains the truth. Pilots who want surprises shouldn't open it in the Mission Editor.

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

## For mission authors

Everything below is for changing or adding missions. You don't need any of it to fly them.

### How the repo works

```
missions/<id>/mission.yaml   source of truth: story, units, route, triggers, briefing
dcsmb/                       the builder (Python)
templates/                   briefing, kneeboard and hangar page layouts
hangar/<id>/                 rendered output: <id>.miz, briefing.html, slides.html, director.html, kneeboard/*.png
scripts/fetch_coastline.py   one-off: coastline data for the slide maps (re-run for a new theater)
Mission Hangar.html          what players open: a shortcut to hangar/index.html
hangar/index.html            home page: campaigns and the single-mission groups
hangar/missions.html         every mission, grouped by campaign, with filters and search
hangar/campaigns/<id>/       campaign page, DCS .cmp and its numbered .miz files
hangar/README.md             the same listing as tables, for GitHub
```

The `.miz`, briefing, slide deck, and kneeboard all come from the same `mission.yaml`, so they can't disagree. **Don't edit files in `hangar/` by hand.** They're overwritten on the next build. That includes saving a `.miz` from the DCS Mission Editor: carry the change back into `mission.yaml` instead.

The hangar is always committed fully rendered. Builds are reproducible: rebuilding an unchanged mission produces byte-identical files, so only missions that actually changed show up in a commit.

### Modify or add a mission

#### 1. Set up (once)

You need Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m playwright install chromium   # renders the kneeboard PNGs
```

#### 2. Edit

Change `missions/<id>/mission.yaml`, or copy an existing mission folder to start a new one (change `meta.id` to match the folder name).

| Section | What it controls |
| --- | --- |
The **Seen by** column says which audience gets each section.

| Section | Seen by | What it controls |
| --- | --- | --- |
| `meta` | everyone | Title, map, date, start time, weather, `category` (`operational` or `training`), `role` (mission type, e.g. Strike, SEAD, CAS, RESCAP, Anti-ship: the hangar filters on it) |
| `training` | pilots (training events only) | `syllabus`, `rules`, `knock_it_off`, `special_subjects`, `grade_sheet` (list of `{item, standard}`), `debrief_focus`. The briefing, slides and kneeboard page 3 render them. |
| `narrative` | pilots, except `outcomes` (director) | Backstory, cast, opening quote. The backstory also becomes the in-game briefing text. |
| `situation`, `objectives`, `roe`, `comms` | pilots | Briefing cards, kneeboard pages, in-game task text |
| `threats` | pilots | **Intel, not truth.** `intel: confirmed / suspected / possible`, optional `area_km` for position uncertainty. Can be wrong on purpose. |
| `flights` | pilots | The player flight: aircraft, `base`/`land` (an airfield or a ship group name), loadout by pylon, waypoints (`action: bomb / sead / cas / cap / antiship`; `agl: true` for terrain-following legs; `timing: {from, seconds, window_s, flag}` for a timed checkpoint that the sim calls early, on time or late and that sets `flag` when on time). A waypoint with `zone_km` gets a trigger zone. |
| `ships` | friendly: pilots; red: director | Ship groups (first type is the lead, e.g. `Stennis`), `route` and `speed_kts`, `tacan`, `icls`, ATC `freq_mhz`, `late_activation` |
| `zones` | director | Extra named trigger zones (e.g. a missile launch line). Usable anywhere a waypoint name is. |
| `target` | pilots (position, description) | `area_km` for an estimated position. What counts as destroyed: `zone_m` (scenery in the zone dies) and/or `groups`, with `kill_pct` (default 100). |
| `units` | director | **Ground truth.** Ground groups, optional `route` and `speed_kmh` for moving units. `late_activation` groups wait for a trigger or variant. `hold_fire: true` for range targets. |
| `support` | friendly: pilots; red: director | `awacs`, `tanker` (with `tacan`), `cap`, `intercept` (scrambles from an airfield), `flight` (spawns in the air and flies a `route`: raids, sweeps, or a helicopter with `task: transport`; route points take `agl: true` and, for helicopters, `land_s` to set down for that many seconds) |
| `variants` | director | Random choices rolled at mission start. Each option can `activate` groups, send a `message`, and wait for a `when`. |
| `storyboard` | `brief` and `notes`: pilots; `script` and `trigger`: director | Ordered phases. `brief` is what pilots are told; `script` is what really happens; `trigger` / `triggers` become DCS trigger rules. |

A trigger's `when` holds one or more conditions, all of which must be true:

- `time_after` (seconds)
- `player_in_zone` (waypoint or zone name; watches your aircraft, not the wingman)
- `group_dead` (group name)
- `group_life_below: [group, percent]` (damaged: e.g. 95 means "anything hit")
- `group_in_zone: [group, zone]`
- `flag` / `flag_false` (a number, or a list that must all be set or all be unset)
- `time_since_flag: [flag, seconds]`
- `player_below_ft` / `player_below_agl_ft` (hard decks and minimum altitudes), `player_above_ft`
- `player_slower_kts` (with `player_below_ft` over the sea: you're on a carrier deck, which is how carrier quals count traps)
- `scenery_dead` (zone name: a map object such as a bridge inside it is destroyed)
- `target_destroyed`
- `variant: [name, option]`

`comms` entries take `radio` and `channel` to land on a cockpit preset. Radio 1 channel 1 is always the flight frequency. Leave them off for scripted-only voices, which appear as on-screen text and don't answer the radio menu.

Add `chance: 1-99` to roll the trigger once at mission start; if the roll misses, the trigger never fires. Actions are `activate`, `deactivate`, `message` (+ `seconds`) and `set_flag`.

Every mission must set **flag 10** on success: the mission's DCS goal scores 100 on it, and campaigns advance on that score.

`meta.weather` can set real DCS weather: `cloud_preset` (a name from `dcs.cloud_presets.Clouds`, e.g. `OvercastAndRain1`) with `cloud_base_ft` inside that preset's range, and `fog_visibility_m`. Without them, `clouds` and `visibility` are briefing text only.

**Campaigns** live in `campaigns/<id>/campaign.yaml`: `id` (the folder name), `title`, `subtitle`, `category`, `setting`, `premise`, `backstory`, `cast`, and `chapters`, a list of `{mission, previously}`. Chapter order is set only here. `previously` is the recap shown on that chapter's brief and deck; it must only repeat what pilots were told, never director-side truth. A campaign mission's `.miz` is built into the campaign folder as `NN_<id>.miz`.

Unit and weapon names are pydcs names. Weapons are the attribute names on `dcs.planes.<Aircraft>.Pylon<N>`, e.g. `dcs.planes.FA_18C_hornet.Pylon2`. The build stops with a clear message if a name, waypoint, or group reference is wrong.

#### 3. Build and commit

```bash
.venv/bin/python -m dcsmb build      # rebuilds every mission and the hangar index
.venv/bin/python -m pytest -q tests  # optional sanity checks
git add missions hangar && git commit
```

Always commit the YAML change and the rebuilt `hangar/` together. `--no-kneeboard` skips Chromium if you only want a quick check of the `.miz` and briefing, but don't commit a build made that way (it drops the kneeboard pages).

#### 4. Check in DCS

DCS doesn't run on the build machine, so after changing positions or triggers, open the `.miz` in the Mission Editor and fly it once. Check that:

- target zones sit on the target (map coordinates come from OpenStreetMap; DCS scenery can be tens of metres off);
- ground units are on sensible terrain;
- radio calls and activations fire when expected;
- random variants really vary: restart the mission a few times and confirm `director.html`'s options all show up.
