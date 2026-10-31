"""Load and validate mission.yaml.

Two audiences live in one file:
  pilot-facing  - narrative (minus outcomes), situation, objectives, roe, threats (intel as
                  briefed, possibly wrong), target, comms, flights, storyboard[].brief/notes
  director-only - units (ground truth), variants, storyboard[].script/triggers, narrative.outcomes
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import yaml

from .geo import BOX


class MissionError(ValueError):
    """Raised when mission.yaml is malformed. Message lists every problem found."""


REQUIRED_TOP = ["meta", "narrative", "situation", "objectives", "flights", "target", "storyboard"]
TRIGGER_WHEN = {"time_after", "player_in_zone", "group_dead", "group_life_below", "group_in_zone", "flag", "flag_false",
                "target_destroyed", "variant", "time_since_flag", "player_below_ft", "player_below_agl_ft",
                "player_slower_kts", "player_above_ft", "scenery_dead"}
CATEGORIES = {"operational", "training"}
SUPPORT_KINDS = {"awacs", "tanker", "cap", "intercept", "flight"}
AI_TASKS = {"antiship", "sweep", "cap", "strike", "transport", "sead"}
INTEL = {"confirmed", "suspected", "possible"}


def load(mission_dir: Path) -> dict:
    path = Path(mission_dir) / "mission.yaml"
    if not path.exists():
        raise MissionError(f"{path} not found")
    data = yaml.safe_load(path.read_text())
    validate(data)
    if data["meta"]["id"] != path.parent.name:
        raise MissionError(f"meta.id '{data['meta']['id']}' must match its folder name '{path.parent.name}'")
    return data


def phase_triggers(ph: dict) -> list[dict]:
    """A phase may give one `trigger` or a list of `triggers`."""
    t = ph.get("triggers", ph.get("trigger"))
    return [] if not t else t if isinstance(t, list) else [t]


def _latlon(obj: dict, where: str, errs: list[str]) -> None:
    for k, lo, hi in (("lat", -90, 90), ("lon", -180, 180)):
        v = obj.get(k)
        if not isinstance(v, (int, float)) or not lo <= v <= hi:
            errs.append(f"{where}: '{k}' must be a number in [{lo}, {hi}], got {v!r}")


def _km(a: dict, b: dict) -> float:
    """Flat-earth distance in km: plenty for the few-km checks here."""
    return math.hypot((a["lat"] - b["lat"]) * 111.0, (a["lon"] - b["lon"]) * 111.0 * math.cos(math.radians(a["lat"])))


def _on_map(obj, box: tuple, theater: str, where: str, errs: list[str]) -> None:
    """Every lat/lon anywhere in the mission must be on the theater's map."""
    if isinstance(obj, dict):
        lat, lon = obj.get("lat"), obj.get("lon")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)) and not (box[0] <= lat <= box[1] and box[2] <= lon <= box[3]):
            errs.append(f"{where or 'mission'}: {lat}, {lon} is off the {theater} map")
        for k, v in obj.items():
            _on_map(v, box, theater, f"{where}.{k}" if where else str(k), errs)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _on_map(v, box, theater, f"{where}[{i}]", errs)


def _check_when(when, where: str, wp_names: set, group_names: set, variants: dict, errs: list[str]) -> None:
    """`when` holds one or more conditions; all must be true for the trigger to fire."""
    when = when or {}
    bad = set(when) - TRIGGER_WHEN
    if not when or bad:
        errs.append(f"{where}.when: needs one or more of {sorted(TRIGGER_WHEN)}" + (f" (unknown: {sorted(bad)})" if bad else ""))
    if "player_in_zone" in when and when["player_in_zone"] not in wp_names:
        errs.append(f"{where}: player_in_zone references unknown waypoint or zone '{when['player_in_zone']}'")
    if "group_in_zone" in when:
        g = when["group_in_zone"]
        if not (isinstance(g, list) and len(g) == 2 and g[0] in group_names and g[1] in wp_names):
            errs.append(f"{where}: group_in_zone must be [known group, waypoint or zone name], got {g!r}")
    if "group_life_below" in when:
        g = when["group_life_below"]
        if not (isinstance(g, list) and len(g) == 2 and g[0] in group_names and 0 < g[1] <= 100):
            errs.append(f"{where}: group_life_below must be [known group, percent of life left], got {g!r}")
    if "time_since_flag" in when:
        t = when["time_since_flag"]
        if not (isinstance(t, list) and len(t) == 2 and all(isinstance(x, int) for x in t)):
            errs.append(f"{where}: time_since_flag must be [flag, seconds], got {t!r}")
    if "scenery_dead" in when and when["scenery_dead"] not in wp_names:
        errs.append(f"{where}: scenery_dead references unknown zone '{when['scenery_dead']}'")
    if "group_dead" in when and when["group_dead"] not in group_names:
        errs.append(f"{where}: group_dead references unknown group '{when['group_dead']}'")
    if "variant" in when:
        v = when["variant"]
        if not (isinstance(v, list) and len(v) == 2 and v[0] in variants and 1 <= v[1] <= variants[v[0]]):
            errs.append(f"{where}: variant must be [variant name, option number], got {v!r}")


def _check_deactivate(names, where: str, group_names: set, errs: list[str]) -> None:
    for g in names or []:
        if g not in group_names:
            errs.append(f"{where}: deactivate references unknown group '{g}'")


def _check_activate(names, where: str, group_names: set, late: set, errs: list[str]) -> None:
    for g in names or []:
        if g not in group_names:
            errs.append(f"{where}: activate references unknown group '{g}'")
        elif g not in late:
            errs.append(f"{where}: activates '{g}', which needs 'late_activation: true' or it is already active")


def validate(data) -> None:
    errs: list[str] = []
    if not isinstance(data, dict):
        raise MissionError("mission.yaml must be a mapping at the top level")

    for k in REQUIRED_TOP:
        if k not in data:
            errs.append(f"missing top-level key '{k}'")
    if errs:
        raise MissionError("\n".join(errs))

    meta = data["meta"]
    for k in ("id", "title", "theater", "date", "start_time"):
        if k not in meta:
            errs.append(f"meta: missing '{k}'")
    if "id" in meta and not re.fullmatch(r"[a-z0-9][a-z0-9_]*", str(meta["id"])):
        errs.append("meta.id: lowercase letters, digits and underscores only (it becomes a folder name in hangar/)")
    if meta.get("category", "operational") not in CATEGORIES:
        errs.append(f"meta.category must be one of {sorted(CATEGORIES)}")
    if meta.get("category") == "training":
        tr = data.get("training") or {}
        if not tr.get("rules") or not tr.get("grade_sheet"):
            errs.append("training: a training event needs 'rules' and a 'grade_sheet' (list of {item, standard})")
        for i, g in enumerate(tr.get("grade_sheet", [])):
            if not (isinstance(g, dict) and g.get("item") and g.get("standard")):
                errs.append(f"training.grade_sheet[{i}]: needs 'item' and 'standard'")
    w = meta.get("weather") or {}
    if w.get("cloud_preset"):
        from dcs.cloud_presets import Clouds
        cp = getattr(Clouds, str(w["cloud_preset"]), None)
        if cp is None:
            errs.append(f"meta.weather.cloud_preset: unknown preset {w['cloud_preset']!r} (see dcs.cloud_presets.Clouds)")
        elif not isinstance(w.get("cloud_base_ft"), int) or not cp.value.min_base <= w["cloud_base_ft"] * 0.3048 <= cp.value.max_base:
            errs.append(f"meta.weather.cloud_base_ft: {w['cloud_preset']} needs a base between "
                        f"{cp.value.min_base / 0.3048:.0f} and {cp.value.max_base / 0.3048:.0f} ft")
    if meta.get("theater") not in BOX:
        errs.append(f"meta.theater: must be one of {sorted(BOX)} (maps the owner has), got {meta.get('theater')!r}")
    else:
        _on_map(data, BOX[meta["theater"]], meta["theater"], "", errs)

    players = [f for f in data["flights"] if f.get("player")]
    if len(players) != 1:
        errs.append(f"flights: exactly one flight must have 'player: true' (found {len(players)})")

    wp_names: set[str] = set()
    for i, f in enumerate(data["flights"]):
        where = f"flights[{i}] ({f.get('callsign', '?')})"
        for k in ("callsign", "aircraft", "base", "waypoints"):
            if k not in f:
                errs.append(f"{where}: missing '{k}'")
        seen = []
        for j, wp in enumerate(f.get("waypoints", [])):
            _latlon(wp, f"{where}.waypoints[{j}]", errs)
            if "name" not in wp:
                errs.append(f"{where}.waypoints[{j}]: missing 'name'")
            tm = wp.get("timing")
            if tm and not (tm.get("from") in seen and isinstance(tm.get("seconds"), int) and isinstance(tm.get("flag"), int)):
                errs.append(f"{where}.waypoints[{j}].timing: needs 'from' (an earlier waypoint), 'seconds' and 'flag'")
            seen.append(wp.get("name"))
            wp_names.add(wp.get("name"))

    # Named zones can be used anywhere a waypoint name is accepted in a trigger
    for i, z in enumerate(data.get("zones", [])):
        _latlon(z, f"zones[{i}] ({z.get('name', '?')})", errs)
        if not z.get("name") or not z.get("radius_km"):
            errs.append(f"zones[{i}]: needs 'name' and 'radius_km'")
        wp_names.add(z.get("name"))

    ship_names = set()
    for i, sh in enumerate(data.get("ships", [])):
        where = f"ships[{i}] ({sh.get('name', '?')})"
        _latlon(sh, where, errs)
        if not sh.get("name") or not sh.get("type"):
            errs.append(f"{where}: needs 'name' and a non-empty 'type' list")
        for j, p in enumerate(sh.get("route", [])):
            _latlon(p, f"{where}.route[{j}]", errs)
        ship_names.add(sh.get("name"))

    for i, s in enumerate(data.get("support", [])):
        where = f"support[{i}] ({s.get('callsign', '?')})"
        if s.get("kind") not in SUPPORT_KINDS:
            errs.append(f"{where}: 'kind' must be one of {sorted(SUPPORT_KINDS)}")
        elif s["kind"] in ("awacs", "tanker"):
            _latlon(s, where, errs)
        elif s["kind"] == "flight":
            _latlon(s.get("spawn") or {}, f"{where}.spawn", errs)
            if s.get("task") not in AI_TASKS:
                errs.append(f"{where}: 'task' must be one of {sorted(AI_TASKS)}")
            if s.get("attack") and s["attack"] not in ship_names:
                errs.append(f"{where}: attack references unknown ship group '{s['attack']}'")

    for i, u in enumerate(data.get("units", [])):
        where = f"units[{i}] ({u.get('name', '?')})"
        _latlon(u, where, errs)
        if not u.get("type"):
            errs.append(f"{where}: 'type' must be a non-empty list of vehicle types")
        for j, p in enumerate(u.get("route", [])):
            _latlon(p, f"{where}.route[{j}]", errs)
    for i, t in enumerate(data.get("threats", [])):
        where = f"threats[{i}] ({t.get('name', '?')})"
        _latlon(t, where, errs)
        if t.get("intel", "confirmed") not in INTEL:
            errs.append(f"{where}: 'intel' must be one of {sorted(INTEL)}")

    group_names = {u["name"] for u in data.get("units", []) if "name" in u}
    group_names |= {s["callsign"] for s in data.get("support", []) if "callsign" in s}
    group_names |= ship_names
    late = {u["name"] for u in data.get("units", []) if u.get("late_activation")}
    late |= {s["callsign"] for s in data.get("support", []) if s.get("late_activation")}
    late |= {sh["name"] for sh in data.get("ships", []) if sh.get("late_activation")}

    tgt = data["target"]
    player = players[0] if len(players) == 1 else {}
    for i, c in enumerate(data.get("comms", [])):
        where = f"comms[{i}] ({c.get('name', '?')})"
        try:
            mhz = float(str(c.get("freq", "")).split()[0])
        except (ValueError, IndexError):
            errs.append(f"{where}: 'freq' must start with the frequency in MHz, e.g. \"251.000 AM\"")
            continue
        if ("radio" in c) != ("channel" in c):
            errs.append(f"{where}: give both 'radio' and 'channel' to put it on a cockpit preset")
        # DCS forces radio 1 channel 1 to the flight's own frequency
        if c.get("radio") == 1 and c.get("channel") == 1 and mhz != player.get("radio1_mhz"):
            errs.append(f"{where}: radio 1 channel 1 is always the flight frequency ({player.get('radio1_mhz')}); use another channel")

    _latlon(tgt, "target", errs)
    for g in tgt.get("groups", []):
        if g not in group_names:
            errs.append(f"target.groups: unknown group '{g}'")
    if not tgt.get("groups") and not tgt.get("zone_m"):
        errs.append("target: needs 'groups' and/or 'zone_m' so target_destroyed can fire")
    # A known target (no area_km) must sit on its vehicles: the briefing, kneeboard and the AI
    # wingman's bombing task all aim at the target point
    placed = {g["name"]: g for g in data.get("units", []) + data.get("ships", []) if "lat" in g and "lon" in g}
    near = [_km(tgt, placed[g]) for g in tgt.get("groups", []) if g in placed]
    if "area_km" not in tgt and "lat" in tgt and near and min(near) > 1:
        errs.append(f"target: point is {min(near):.1f} km from the nearest target group; "
                    "move it onto the group or give the target an area_km")
    if not 0 < tgt.get("kill_pct", 100) <= 100:
        errs.append("target.kill_pct: must be in (0, 100]")

    variants = {v.get("name"): len(v.get("options", [])) for v in data.get("variants", [])}
    flags = set()
    for i, v in enumerate(data.get("variants", [])):
        where = f"variants[{i}] ({v.get('name', '?')})"
        if not v.get("name") or len(v.get("options", [])) < 2:
            errs.append(f"{where}: needs a 'name' and at least two 'options'")
        if v.get("flag") in flags:
            errs.append(f"{where}: flag {v['flag']} is used twice")
        flags.add(v.get("flag"))
        for j, o in enumerate(v.get("options", [])):
            _check_activate(o.get("activate"), f"{where}.options[{j}]", group_names, late, errs)
            if "when" in o:
                _check_when(o["when"], f"{where}.options[{j}]", wp_names, group_names, variants, errs)

    for i, ph in enumerate(data["storyboard"]):
        where = f"storyboard[{i}] ({ph.get('phase', '?')})"
        if "phase" not in ph or "brief" not in ph:
            errs.append(f"{where}: needs 'phase' and 'brief' (what the pilots are told)")
        for w in ph.get("waypoints", []):
            if w not in wp_names:
                errs.append(f"{where}: unknown waypoint '{w}'")
        for j, trig in enumerate(phase_triggers(ph)):
            tw = f"{where}.triggers[{j}]"
            _check_when(trig.get("when"), tw, wp_names, group_names, variants, errs)
            _check_activate(trig.get("activate"), tw, group_names, late, errs)
            _check_deactivate(trig.get("deactivate"), tw, group_names, errs)
            if "chance" in trig and not 0 < trig["chance"] < 100:
                errs.append(f"{tw}: 'chance' is a percentage between 1 and 99")

    sets = [t.get("set_flag") for ph in data["storyboard"] for t in phase_triggers(ph)]
    sets += [o.get("set_flag") for v in data.get("variants", []) for o in v.get("options", [])]
    if 10 not in sets:
        errs.append("no trigger sets flag 10, the success flag (the mission goal and DCS campaigns score on it)")

    if errs:
        raise MissionError("\n".join(errs))


def load_campaigns(campaigns_dir: Path, missions: list[dict]) -> list[dict]:
    """Load every campaigns/<id>/campaign.yaml, check it against the missions, and tag each chapter's mission.

    campaign.yaml is the only place chapter order lives. Each chapter's mission gets
    data["campaign"] = {id, title, chapter, of, previously} for the page builders.
    """
    by_id = {m["meta"]["id"]: m for m in missions}
    out, owner, errs = [], {}, []
    for path in sorted(Path(campaigns_dir).glob("*/campaign.yaml")):
        c = yaml.safe_load(path.read_text())
        where = f"campaigns/{path.parent.name}"
        for k in ("id", "title", "premise", "chapters"):
            if not c.get(k):
                errs.append(f"{where}: missing '{k}'")
        if c.get("id") and c["id"] != path.parent.name:
            errs.append(f"{where}: id '{c['id']}' must match its folder name")
        cat = c.get("category", "operational")
        if cat not in CATEGORIES:
            errs.append(f"{where}: category must be one of {sorted(CATEGORIES)}")
        last_date = None
        for i, ch in enumerate(c.get("chapters") or [], 1):
            mid = ch.get("mission")
            m = by_id.get(mid)
            if m is None:
                errs.append(f"{where}: chapter {i} references unknown mission '{mid}'")
                continue
            if mid in owner:
                errs.append(f"{where}: mission '{mid}' is already chapter of campaign '{owner[mid]}'")
            owner[mid] = c.get("id")
            if m["meta"].get("category", "operational") != cat:
                errs.append(f"{where}: chapter {i} ({mid}) is {m['meta'].get('category', 'operational')}, campaign is {cat}")
            d = str(m["meta"]["date"])
            if last_date and d < last_date:
                errs.append(f"{where}: chapter {i} ({mid}) is dated {d}, before the chapter it follows ({last_date})")
            last_date = d
            if i == 1 and ch.get("previously"):
                errs.append(f"{where}: chapter 1 can't have 'previously'")
        out.append(c)
    if errs:
        raise MissionError("\n".join(errs))
    out.sort(key=lambda c: str(by_id[c["chapters"][0]["mission"]]["meta"]["date"]))  # story order
    for c in out:
        n = len(c["chapters"])
        for i, ch in enumerate(c["chapters"], 1):
            by_id[ch["mission"]]["campaign"] = {"id": c["id"], "title": c["title"], "chapter": i, "of": n,
                                                "previously": (ch.get("previously") or "").strip()}
    return out
