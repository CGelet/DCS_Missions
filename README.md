# DCS Missions

Each mission is one YAML file. From it the builder generates:

- **`<id>.miz`**: a playable DCS mission (units, waypoints, loadouts, triggers, briefing text, kneeboard pages)
- **`briefing.html`**: an interactive briefing page with the story, a clickable storyboard tied to a Leaflet map, briefing cards, and the possible outcomes
- **`kneeboard/*.png`**: 768×1024 pages that also get packed into the `.miz`

The `.miz` and the briefing come from the same file, so they can't drift apart.

## Setup

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m playwright install chromium   # only needed for kneeboard PNGs
```

## Build

```bash
.venv/bin/python -m dcsmb build missions/gudauta_bridge            # everything
.venv/bin/python -m dcsmb build missions/gudauta_bridge --no-kneeboard
.venv/bin/python -m pytest -q tests
```

Output goes to `out/<id>/`. Copy the `.miz` to `Saved Games/DCS/Missions/` and open it in the Mission Editor.

## Writing a mission

Copy `missions/gudauta_bridge/` and edit `mission.yaml`. The sections:

| Section | Feeds |
| --- | --- |
| `meta` | Date, time, and weather in the .miz; header of the briefing |
| `narrative` | Backstory, cast, opening quote, and success/partial/failure debriefs. The backstory also becomes the in-game briefing text. |
| `situation`, `objectives`, `roe`, `threats`, `comms` | Briefing cards, kneeboard, in-game task text |
| `flights` | The player flight: airframe, base, loadout (by pylon), and waypoints. A waypoint with `zone_km` gets a trigger zone. |
| `units`, `support` | Ground groups, AWACS, CAP, and red interceptors. `late_activation` groups wait for a trigger. |
| `storyboard` | Ordered story phases. Each one has a narrative `beat` and an optional `trigger` that becomes a DCS trigger rule (radio message, group activation, flag). |

Trigger conditions: `time_after`, `player_in_zone` (waypoint name), `group_dead`, `flag`, and `target_destroyed`. `target_destroyed` fires when the scenery object in the target zone dies, or when the fallback `Bridge target` group does.

`build_miz.py` validates unit and weapon names against pydcs. Weapon names are the attribute names on `dcs.planes.<Aircraft>.Pylon<N>`.

## Check in the Mission Editor

DCS doesn't run on the build machine, so a few things need eyes in the editor:

- The `TARGET BRIDGE` zone should sit on the bridge deck. The coordinates come from OpenStreetMap, and DCS scenery can be offset by tens of metres.
- The SA-6 and AAA should be on sensible ground, not in a river or on a slope.
- Fly the mission once to confirm the radio calls fire at the IP, the target, and on bridge destruction.
