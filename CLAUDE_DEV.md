# CLAUDE_DEV.md

Working notes for Claude on this repo. This is a draft that will become `CLAUDE.md`. Add to it whenever something is learned, decided or corrected. Keep entries short and say *why*.

## What this project is

A hangar of DCS World missions. Each mission is one `missions/<id>/mission.yaml`, and from it the builder (`dcsmb/`) renders:

- `hangar/<id>/<id>.miz`: playable mission (pydcs)
- `hangar/<id>/briefing.html`: interactive briefing (story, storyboard ↔ Leaflet map, briefing cards, outcomes)
- `hangar/<id>/slides.html`: presenter deck that tells the mission as a story
- `hangar/<id>/kneeboard/*.png`: 768×1024 kneeboard pages, also packed into the `.miz`
- `hangar/index.html`, `hangar/README.md`: the hangar listing

## Owner decisions (don't relitigate)

- **One YAML is the source of truth.** Every output is generated from it so nothing drifts. Never hand-edit `hangar/`.
- **Claude renders everything and commits the full renders.** The repo *is* the hangar; pilots download and fly without installing anything. GitHub Actions and GitHub-side builds were discussed and declined in favour of this.
- **Keep it easy for others.** The scripts and instructions to modify missions stay in the repo (README "Modify or add a mission"), but nobody is expected to build.
- **Minimise dependencies for users.** Heavy tools (Chromium via Playwright) only run on Claude's side.
- **Story is first-class.** Every mission gets a backstory, cast, hook quote, per-phase beats, in-sim radio calls and success/partial/failure debriefs. The owner loves the HTML briefing; slides were added for presenting the story.
- This file is to be developed collaboratively and later promoted to `CLAUDE.md`.

## Workflow rules for Claude

1. After **any** mission or template change, rebuild **all** missions: `.venv/bin/python -m dcsmb build` (without `--no-kneeboard`).
2. Run `.venv/bin/python -m pytest -q tests`.
3. Look at the output: screenshot pages with Playwright, check for console errors, check 390 px mobile width (no horizontal scroll), and view slide maps for label collisions and framing.
4. Commit the YAML change and the rebuilt `hangar/` **together**, then push to `origin master` (`CGelet/DCS_Missions`).
5. Builds must stay **byte-reproducible**. To check, build twice and compare sha1s of `hangar/**`. If something starts diffing on every build, find the randomness (see pydcs gotchas).

## Environment facts

- The host has no `pip`, `ensurepip` or `unzip`. `uv` is installed at `~/.local/bin/uv`, the venv is `.venv/` (created with `uv venv`), and packages are installed with `uv pip install --python .venv/bin/python -r requirements.txt`.
- Chromium for Playwright: `.venv/bin/python -m playwright install chromium`.
- **DCS is not installed and can't run here.** Anything that depends on the sim (zone placement on scenery, trigger timing, AI behaviour) must be flagged for the owner to verify in the Mission Editor.
- To inspect a `.miz`, use Python's `zipfile` (there's no `unzip`).

## pydcs gotchas (v0.15.0)

- **Import noise:** on Linux it prints "Couldn't detect any installed DCS World version" hundreds of times. `dcsmb/__init__.py` silences it, so always `import dcsmb` before `dcs`.
- **Hidden randomness breaks reproducible builds:**
  - `add_runway_waypoint(distance=random.randrange(...))` draws its default when the module is imported. Seed `random` *before* importing pydcs (done in `dcsmb/__init__.py`).
  - Tail numbers come from `set.pop()`, which depends on hash randomisation, not `random`. We assign them in order in `build_miz.py`.
  - Zip entry timestamps are pinned by `_pin_zip_timestamps`.
- **"Map object is dead" is zone-based:** `condition.MapObjectIsDead(zone_id)` (`c_dead_zone`). No scenery object ID is needed; a small trigger zone on the target works.
- Use **vehicle groups, not statics**, for anything a `GroupDead` trigger watches.
- Kneeboards: `mission.add_aircraft_kneeboard(aircraft_type, path)` writes to `KNEEBOARD/<type id>/IMAGES/`. Pages are per aircraft type, not per flight.
- Weapons are attributes on `dcs.planes.<Type>.Pylon<N>` (e.g. `FA_18C_hornet.Pylon2.BRU_33_with_2_x_GBU_12___500lb_Laser_Guided_Bomb`). Clear `unit.pylons = {}` before loading.
- Vehicle types live in category classes: `dcs.vehicles.AirDefence.Kub_1S91_str`, `Unarmed.Ural_375`, etc. (`_vehicle()` searches them).
- Airports: `terrain.airports` keys are display names (`"Senaki-Kolkhi"`). `_airport()` accepts `Senaki_Kolkhi` style.
- Coordinates: `mapping.Point.from_latlng(LatLng(lat, lon), terrain)` and `point.latlng()` round-trip exactly, so the HTML/slide maps and the `.miz` agree.

## Template gotchas

- Jinja: never name a dict key `items`, `keys` or `values`. `s.items` resolves to the dict method (this happened with slides; renamed to `entries`).
- f-strings in Python 3.10 can't contain backslashes in expressions; build the fragment in a variable first.
- `select_autoescape(["html","j2"])` escapes `.md.j2` too. Wrap Markdown templates in `{% autoescape false %}`.
- Leaflet tiles: CARTO basemaps now need an API key ("API KEY REQUIRED" watermark). Use Esri `World_Topo_Map` (light) and `Canvas/World_Dark_Gray_Base` (dark), which need no key.
- Slide maps are inline SVG (offline). `Labels` does simple collision avoidance; route labels get first pick. Deduplicate the home base (it's both the first and last route point).

## Geography: verify, don't guess

- **My first target coordinates were wrong** (put the "Bzyb bridge" near Gagra). Real-terrain map tiles exposed it. Always look up real-world features in OpenStreetMap before placing targets:
  - Overpass, e.g. `way["bridge"]["highway"~"trunk|primary"](S,W,N,E);out center tags;` at `https://overpass-api.de/api/interpreter`. It's often overloaded (502/timeouts): retry with backoff, keep queries small, and send a User-Agent.
  - Nominatim reverse geocoding (`/reverse?format=jsonv2&lat=..&lon=..`) to identify places. One request per second.
  - Trick that worked: the Bzyb River is the Gagra/Gudauta district boundary, so bridge ends geocoding to different districts confirmed the crossing.
- Even with OSM coordinates, DCS scenery can be tens of metres off, so always ask the owner to check target zones in the Mission Editor.
- **Story text must match the map.** I once had an AWACS call say the SA-6 was "northeast" when it was east-southeast. Check directions and distances in radio calls against coordinates.
- Coastline for slide maps: `scripts/fetch_coastline.py <theater> S W N E` → `dcsmb/data/coast_<theater>.json` (OSM, ODbL). It needs re-running for each new theater.

## Storytelling conventions

- Narrative layers, each for a moment: **slides** (group brief, spoken), **briefing.html** (self-paced reference), **radio calls** (live in the cockpit), **kneeboard** (facts in the cockpit), **outcomes** (debrief).
- Backstory: 2–3 short paragraphs. The first sets the conflict; the next says why *this* target matters. Each becomes one slide.
- Hook: a single quoted line from a character, attributed.
- Cast: 3–5 entries, including the voices heard on the radio (AWACS, commander, ground liaison) and the player flight.
- Phase beats: 2–3 sentences, present tense, sensory, ending on tension. Radio calls look like `CALLSIGN: message`, are terse and brevity-ish, and fit on one DCS message line.
- Outcomes: success, partial and failure, each with a concrete consequence that could seed the next mission.
- Presenter `notes` on phases: prompts for the briefer (pause points, questions for the room).
- All people and units are fictional. Use real geography and real aircraft and systems.

## Mission content conventions

- The player flight has `player: true` (exactly one). Waypoints that triggers reference need `zone_km` (default 10 km).
- Threat-based story beats use `late_activation` groups activated by `player_in_zone` triggers.
- `target_destroyed` = scenery object in the `TARGET BRIDGE` zone dead **OR** fallback group `Bridge target` dead (two helper rules setting flag 99).

## Open ideas (not started)

- GitHub Pages serving `hangar/` so briefings and slides are clickable links (one setting in the repo, no build).
- Campaign chaining: one mission's outcomes feed the next mission's backstory.
- Optional base `.miz` overlay for owners who want to hand-edit in the Mission Editor.
- A committed PDF of each deck (Chromium PDFs embed a creation date; strip it to keep builds reproducible).
- More theaters (needs coastline data plus a `Caucasus()`-style terrain switch in `build_miz`/`build_html`, which are currently Caucasus-only).
