"""Load and validate mission.yaml.

Two audiences live in one file:
  pilot-facing  - narrative (minus outcomes), situation, objectives, roe, threats (intel as
                  briefed, possibly wrong), target, comms, flights, storyboard[].brief/notes
  director-only - units (ground truth), variants, storyboard[].script/triggers, narrative.outcomes
"""
from __future__ import annotations

from pathlib import Path

import yaml


class MissionError(ValueError):
    """Raised when mission.yaml is malformed. Message lists every problem found."""


REQUIRED_TOP = ["meta", "narrative", "situation", "objectives", "flights", "target", "storyboard"]
TRIGGER_WHEN = {"time_after", "player_in_zone", "group_dead", "flag", "target_destroyed", "variant"}
INTEL = {"confirmed", "suspected", "possible"}


def load(mission_dir: Path) -> dict:
    path = Path(mission_dir) / "mission.yaml"
    if not path.exists():
        raise MissionError(f"{path} not found")
    data = yaml.safe_load(path.read_text())
    validate(data)
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


def _check_when(when, where: str, wp_names: set, group_names: set, variants: dict, errs: list[str]) -> None:
    """`when` holds one or more conditions; all must be true for the trigger to fire."""
    when = when or {}
    bad = set(when) - TRIGGER_WHEN
    if not when or bad:
        errs.append(f"{where}.when: needs one or more of {sorted(TRIGGER_WHEN)}" + (f" (unknown: {sorted(bad)})" if bad else ""))
    if "player_in_zone" in when and when["player_in_zone"] not in wp_names:
        errs.append(f"{where}: player_in_zone references unknown waypoint '{when['player_in_zone']}'")
    if "group_dead" in when and when["group_dead"] not in group_names:
        errs.append(f"{where}: group_dead references unknown group '{when['group_dead']}'")
    if "variant" in when:
        v = when["variant"]
        if not (isinstance(v, list) and len(v) == 2 and v[0] in variants and 1 <= v[1] <= variants[v[0]]):
            errs.append(f"{where}: variant must be [variant name, option number], got {v!r}")


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
    if meta.get("theater") != "caucasus":
        errs.append(f"meta.theater: only 'caucasus' is supported so far, got {meta.get('theater')!r}")

    players = [f for f in data["flights"] if f.get("player")]
    if len(players) != 1:
        errs.append(f"flights: exactly one flight must have 'player: true' (found {len(players)})")

    wp_names: set[str] = set()
    for i, f in enumerate(data["flights"]):
        where = f"flights[{i}] ({f.get('callsign', '?')})"
        for k in ("callsign", "aircraft", "base", "waypoints"):
            if k not in f:
                errs.append(f"{where}: missing '{k}'")
        for j, wp in enumerate(f.get("waypoints", [])):
            _latlon(wp, f"{where}.waypoints[{j}]", errs)
            if "name" not in wp:
                errs.append(f"{where}.waypoints[{j}]: missing 'name'")
            wp_names.add(wp.get("name"))

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
    late = {u["name"] for u in data.get("units", []) if u.get("late_activation")}
    late |= {s["callsign"] for s in data.get("support", []) if s.get("late_activation")}

    tgt = data["target"]
    _latlon(tgt, "target", errs)
    for g in tgt.get("groups", []):
        if g not in group_names:
            errs.append(f"target.groups: unknown group '{g}'")
    if not tgt.get("groups") and not tgt.get("zone_m"):
        errs.append("target: needs 'groups' and/or 'zone_m' so target_destroyed can fire")
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
            if "chance" in trig and not 0 < trig["chance"] < 100:
                errs.append(f"{tw}: 'chance' is a percentage between 1 and 99")

    if errs:
        raise MissionError("\n".join(errs))
