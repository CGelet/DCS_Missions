# DCS Missions

A hangar of ready-to-fly DCS World missions, each with a full story, an interactive briefing, and kneeboard pages.

## Fly a mission (no install needed)

Everything in [`hangar/`](hangar/) is already rendered:

1. Open [`hangar/README.md`](hangar/README.md) to browse the missions.
2. Download the mission's `.miz` and put it in `Saved Games/DCS/Missions/`.
3. Download its `briefing.html` and open it in a browser for the story, the storyboard map, and the briefing cards. GitHub shows HTML files as source code, so download it rather than viewing it on GitHub.
4. The kneeboard pages are already inside the `.miz`. The PNGs are in the repo too, if you want to print them.

## How the repo works

```
missions/<id>/mission.yaml   source of truth: story, units, route, triggers, briefing
dcsmb/                       the builder (Python)
templates/                   briefing, kneeboard and hangar page layouts
hangar/<id>/                 rendered output: <id>.miz, briefing.html, kneeboard/*.png
hangar/index.html, README.md hangar listing, regenerated on every build
```

The `.miz`, briefing, and kneeboard all come from the same `mission.yaml`, so they can't disagree. **Don't edit files in `hangar/` by hand.** They're overwritten on the next build. That includes saving a `.miz` from the DCS Mission Editor: carry the change back into `mission.yaml` instead.

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
| `meta` | Title, map, date, start time, weather |
| `narrative` | Backstory, cast, opening quote, success/partial/failure debriefs. The backstory also becomes the in-game briefing text. |
| `situation`, `objectives`, `roe`, `threats`, `comms` | Briefing cards, kneeboard pages, in-game task text |
| `flights` | The player flight: aircraft, base, loadout by pylon, waypoints. A waypoint with `zone_km` gets a trigger zone. |
| `target` | Target position. `zone_m` is the radius of the "map object dead" zone. |
| `units`, `support` | Ground groups, AWACS, CAP, red interceptors. `late_activation` groups wait for a trigger. |
| `storyboard` | Ordered story phases. Each has a narrative `beat` and an optional `trigger` that becomes a DCS trigger rule (radio message, group activation, flag). |

Trigger conditions: `time_after` (seconds), `player_in_zone` (waypoint name), `group_dead` (group name), `flag` (number), and `target_destroyed`. `target_destroyed` fires when the scenery object in the target zone dies, or when the `Bridge target` fallback group does.

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
- radio calls and activations fire when expected.
