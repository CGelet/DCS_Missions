# CLAUDE_DEV.md

Working notes for Claude on this repo. This is a draft that will become `CLAUDE.md`. Add to it whenever something is learned, decided or corrected. Keep entries short and say *why*.

## What this project is

A hangar of DCS World missions. Each mission is one `missions/<id>/mission.yaml`, and from it the builder (`dcsmb/`) renders:

- `hangar/<id>/<id>.miz`: playable mission (pydcs)
- `hangar/<id>/briefing.html`: interactive briefing (story, storyboard ↔ Leaflet map, briefing cards, outcomes)
- `hangar/<id>/slides.html`: presenter deck that tells the mission as a story
- `hangar/<id>/director.html`: spoiler view (intel vs truth, random rolls, triggers, outcomes)
- `hangar/<id>/kneeboard/*.png`: 768×1024 kneeboard pages, also packed into the `.miz`
- `hangar/index.html`, `hangar/README.md`: the hangar listing

## Owner decisions (don't relitigate)

- **One YAML is the source of truth.** Every output is generated from it so nothing drifts. Never hand-edit `hangar/`.
- **Claude renders everything and commits the full renders.** The repo *is* the hangar; pilots download and fly without installing anything. GitHub Actions and GitHub-side builds were discussed and declined in favour of this.
- **Keep it easy for others.** The scripts and instructions to modify missions stay in the repo (README "Modify or add a mission"), but nobody is expected to build.
- **Minimise dependencies for users.** Heavy tools (Chromium via Playwright) only run on Claude's side.
- **Story is first-class.** Every mission gets a backstory, cast, hook quote, per-phase beats, in-sim radio calls and success/partial/failure debriefs. The owner loves the HTML briefing; slides were added for presenting the story.
- This file is to be developed collaboratively and later promoted to `CLAUDE.md`.
- **Briefings must not give away the mission.** (2026-10-27: the owner flagged "Ten seconds later the RWR lights up with a six" as something pilots couldn't know.) Pilot-facing outputs carry only the plan and intel at brief time. Everything that happens, plus hidden units and outcomes, goes in `director.html`.
- **Use real uncertainty, not just hidden text.** Intel has confidence levels and can be wrong on purpose; DCS-side randomness (`variants`, `chance`) means even the director doesn't know the exact flight.

## Workflow rules for Claude

1. After **any** mission or template change, rebuild **all** missions: `.venv/bin/python -m dcsmb build` (without `--no-kneeboard`).
2. Run `.venv/bin/python -m pytest -q tests`.
3. Look at the output: screenshot pages with Playwright, check for console errors, check 390 px mobile width (no horizontal scroll), and view slide maps for label collisions and framing.
4. Commit the YAML change and the rebuilt `hangar/` **together**, then push to `origin master` (`CGelet/DCS_Missions`).
5. Builds must stay **byte-reproducible**. To check, build twice and compare sha1s of `hangar/**`. If something starts diffing on every build, find the randomness (see pydcs gotchas).

## Pilot vs director: the core authoring rule

- `threats` = **intel** (what the squadron is told; may be stale, vague or wrong). `units` = **truth**. Never derive one from the other.
- Storyboard `brief` = the plan in future/conditional voice ("If the SA-6 is still there..."). `script` = what actually happens. Never write a `brief` that asserts an event.
- Presenter `notes` ship inside `slides.html`, so keep them spoiler-free (prompts and questions for the room).
- Red `support` flights, target `groups`/`kill_pct`/`zone_m`, late-activated unit names, variant labels, trigger messages and `outcomes` are director-only. `view_model(audience="pilot")` filters them out.
- `tests/test_build.py::test_pilot_outputs_have_no_spoilers` checks every mission. It already caught two real leaks: the map JSON carried `target.groups`, and the slides read raw `support`. When adding pilot-facing fields, extend `_spoilers()` if anything new is director-only.
- The `.miz` necessarily contains the truth; that's accepted.

## Story devices tried so far (vary them across missions)

| Mission | Device | Mechanics |
| --- | --- | --- |
| BROKEN SPAN (F/A-18C) | Stale intel | SA-6 "suspected" 2 km from its real spot; MiGs "possible", 70% chance to launch |
| SILENT ORCHARD (F-16C) | The hunt | SA-11 at one of two hides (`variants`); hint radio call gated on the variant; unbriefed-ish SA-8 at 50%; MiGs 30% |
| HOLD FAST (A-10C II) | Ticking clock and branching ending | Attack axis is a variant that spawns on check-in; moving columns (`route`); success vs friendly position destroyed |
| BLUE WATER (F-14B, carrier) | The threat you can't see, and gas you can't count on | Raid axis variant spawns on reaching CAP; 40% Flanker sweep; 30% the tanker is `deactivate`d before you reach it; `group_in_zone` launch-line failure; recover aboard a moving carrier |
| DEEP CUT (AV-8B) | The long way round | Tanker, then AGL valley route; target is apron or moving convoy (variant, hint at Pskhu); 50% Tor; 40% MiG scramble; lands at a different field |

**Make routes look and fly differently** (owner feedback 2026-10-27: "all of these flight paths seem to be the same"). Vary the base (carrier or other field), the recovery field, refuelling, orbits (CAP or holding), AGL legs, pop-ups and egress direction. The altitude profile (`profile_svg`) makes the difference visible.

Ideas not yet used: deception (a decoy SAM that's briefed as confirmed), weather turning, CSAR or rescue, escort of a slow friendly, a mission whose intel depends on the previous mission's outcome.

The missions form a campaign (same world, cast and dates in order). The hangar sorts by `meta.date`. Write backstories that work whatever the previous outcome was.

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

- **Trigger plumbing** (`build_miz.py`): flag 99 = target destroyed; 200+ = `chance` rolls (`TriggerStart` + `Random(pct)` → flag); 300+ = variant flags (`TriggerStart` + `SetFlagRandom(flag, 1, n)`, then one `TriggerOnce` per option on `FlagEquals`).
- **Not verified in-sim, needs the owner to check:** that `SetFlagRandom` bounds are inclusive (all options reachable), and how `GroupDead`/`GroupLifeLess` behave on a late-activation group that never spawned. Target helpers are gated on the variant's flag so an unspawned group can't count either way.
- **Weapon names aren't consistent across pylons:** A-10C II pylon 3 is `LAU_88_with_2_x_AGM_65D___Maverick_D__IIR_ASM_` but pylon 9 is `...ASM__` (double underscore). `_weapon()` now lists similar names on a miss. Use it to discover names rather than guessing.
- **Radios (owner report 2026-10-27: "the radio is giving no responses"):** pydcs leaves the player's presets at DCS defaults, so only radio 1 channel 1 (the group frequency) was useful and the tower was on no preset. Now every `comms` entry with `radio`/`channel` goes onto the player aircraft's presets (`_set_presets`), and the comms card, kneeboard and slides show the preset in that cockpit's radio names (`RADIO_NAMES`). DCS forces radio 1 channel 1 to the flight frequency, and the schema enforces that. Check which radio can tune the frequency: the F-16's radio 1 is UHF-only, so VHF towers go on radio 2.
- **Callsigns:** pydcs gives flights default callsigns, so the "Colt" CAP was really "Springfield 1-1" in the comms menu. `_set_callsign` maps the YAML callsign onto the country list (`country.callsign["Air"/"AWACS"]`), followed by the type's own `callnames` (A-10: Hawg = 9). Red/Russian callsigns are numeric and left alone.
- **Scripted voices aren't radio stations.** HATCH, CHISEL and Kapanadze are on-screen trigger text, not DCS JTAC/ATC, so they never answer the F5 menu. Mark them that way on the comms card so nobody expects a reply.
- **`player_in_zone` uses the lead unit** (`UnitInZone(units[0])`), not `PartOfGroupInZone`. Owner report: a waypoint-1 call came "before we even took off". Most likely the AI wingman launched alone and tripped the group-based zone. Story beats must follow the human.
- `task.SEAD`, `task.CAS` and `task.GroundAttack` are the main tasks; waypoint `action` picks the main task and AI wingman tasks.
- Ground-unit routes use `VehicleGroup.add_waypoint(point, PointAction.OnRoad, speed_kmh)`.
- **Carriers:** `flight_group_from_unit(..., ship_group)` for deck starts. Landing aboard is a hand-built `MovingPoint` (`type="Land"`, `action=Landing`, `link_unit` and `helipad_id` = carrier unit id); see `_land_on_ship`. Ship TACAN uses `ActivateBeaconCommand(..., aa=False, unit_id=carrier)`, plus `ActivateICLSCommand`. The ship's ATC frequency is `ShipGroup.set_frequency(hz)`, in hertz. The carrier moves, so maps draw the recovery at the end of the ship's route.
- **Tankers:** `refuel_flight` creates a TACAN beacon with no unit id or callsign; `build_miz` replaces it. Tanker callsigns come from `country.callsign["Tankers"]`.
- **No flyable F-15E in pydcs 0.15.0** (only the AI `F_15E`). Flyable player types used so far: FA_18C_hornet, F_16C_50, A_10C_2, F_14B, AV8BNA. Check `.flyable` before planning a mission.
- AGL legs are `MovingPoint.alt_type = "RADIO"`.

## Template gotchas

- Jinja: never name a dict key `items`, `keys` or `values`. `s.items` resolves to the dict method (this happened with slides; renamed to `entries`).
- f-strings in Python 3.10 can't contain backslashes in expressions; build the fragment in a variable first.
- `select_autoescape(["html","j2"])` escapes `.md.j2` too. Wrap Markdown templates in `{% autoescape false %}`.
- Leaflet tiles: CARTO basemaps now need an API key ("API KEY REQUIRED" watermark). Use Esri `World_Topo_Map` (light) and `Canvas/World_Dark_Gray_Base` (dark), which need no key.
- Shared page CSS lives in `templates/_base.css`, included by `briefing.html.j2` and `director.html.j2` (`{% include %}`; keep Jinja syntax out of it).
- Slide maps are inline SVG (offline). `Labels` does simple collision avoidance; route labels get first pick. Deduplicate the home base (it's both the first and last route point).

## Geography: verify, don't guess

- **My first target coordinates were wrong** (put the "Bzyb bridge" near Gagra). Real-terrain map tiles exposed it. Always look up real-world features in OpenStreetMap before placing targets:
  - Overpass, e.g. `way["bridge"]["highway"~"trunk|primary"](S,W,N,E);out center tags;` at `https://overpass-api.de/api/interpreter`. It's often overloaded (502/timeouts): retry with backoff, keep queries small, and send a User-Agent.
  - Nominatim reverse geocoding (`/reverse?format=jsonv2&lat=..&lon=..`) to identify places. One request per second.
  - Trick that worked: the Bzyb River is the Gagra/Gudauta district boundary, so bridge ends geocoding to different districts confirmed the crossing.
- Even with OSM coordinates, DCS scenery can be tens of metres off, so always ask the owner to check target zones in the Mission Editor.
- **Story text must match the map.** I once had an AWACS call say the SA-6 was "northeast" when it was east-southeast. Check directions and distances in radio calls against coordinates.
- Nominatim reverse geocoding is a good land-or-sea and which-district check for every ground unit position. It was used for all of SILENT ORCHARD and HOLD FAST.
- Gumista crossings (OSM): coast road bridge 43.0163N 40.9498E, highway bridge 43.0553N 40.9969E.
- Coastline for slide maps: `scripts/fetch_coastline.py <theater> S W N E` → `dcsmb/data/coast_<theater>.json` (OSM, ODbL). It needs re-running for each new theater.

## Storytelling conventions

- Narrative layers, each for a moment: **slides** (group brief, spoken), **briefing.html** (self-paced reference), **radio calls** (live in the cockpit), **kneeboard** (facts in the cockpit), **outcomes** (debrief).
- Backstory: 2–3 short paragraphs. The first sets the conflict; the next says why *this* target matters. Each becomes one slide.
- Hook: a single quoted line from a character, attributed.
- Cast: 3–5 entries, including the voices heard on the radio (AWACS, commander, ground liaison) and the player flight.
- Phase `brief`: 2–3 sentences: the plan, what to expect, and what to be ready for, written as expectation rather than fact. Phase `script`: plain description of the truth, with odds.
- Radio calls look like `CALLSIGN: message`, are terse and brevity-ish, and fit on one DCS message line.
- Outcomes: success, partial and failure, each with a concrete consequence that could seed the next mission. They're director-only; read them at the debrief.
- Presenter `notes` on phases: prompts for the briefer (pause points, questions for the room).
- All people and units are fictional. Use real geography and real aircraft and systems.

## Mission content conventions

- The player flight has `player: true` (exactly one). Waypoints that triggers reference need `zone_km` (default 10 km).
- Threat-based story beats use `late_activation` groups activated by `player_in_zone` triggers.
- `target_destroyed` = scenery object in the `TARGET BRIDGE` zone dead **OR** fallback group `Bridge target` dead (two helper rules setting flag 99).

## Open ideas (not started)

- `scripts/check_pages.py`: the Playwright checks I run by hand (screenshots, console errors, 390 px width, PDF page count), so others can repeat them.
- Merge labels of co-located threats on slide maps (HOLD FAST's column, Shilka and MANPADS share one estimate).

- GitHub Pages serving `hangar/` so briefings and slides are clickable links (one setting in the repo, no build).
- Campaign chaining: one mission's outcomes feed the next mission's backstory.
- Optional base `.miz` overlay for owners who want to hand-edit in the Mission Editor.
- A committed PDF of each deck (Chromium PDFs embed a creation date; strip it to keep builds reproducible).
- More theaters (needs coastline data plus a `Caucasus()`-style terrain switch in `build_miz`/`build_html`, which are currently Caucasus-only).
