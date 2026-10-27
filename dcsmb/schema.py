"""Load and validate mission.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml


class MissionError(ValueError):
    """Raised when mission.yaml is malformed. Message lists every problem found."""


REQUIRED_TOP = ["meta", "narrative", "situation", "objectives", "flights", "target", "storyboard"]
TRIGGER_WHEN = {"time_after", "player_in_zone", "group_dead", "flag", "target_destroyed"}


def load(mission_dir: Path) -> dict:
    path = Path(mission_dir) / "mission.yaml"
    if not path.exists():
        raise MissionError(f"{path} not found")
    data = yaml.safe_load(path.read_text())
    validate(data)
    return data


def _latlon(obj: dict, where: str, errs: list[str]) -> None:
    for k, lo, hi in (("lat", -90, 90), ("lon", -180, 180)):
        v = obj.get(k)
        if not isinstance(v, (int, float)) or not lo <= v <= hi:
            errs.append(f"{where}: '{k}' must be a number in [{lo}, {hi}], got {v!r}")


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

    _latlon(data["target"], "target", errs)
    for i, u in enumerate(data.get("units", [])):
        _latlon(u, f"units[{i}] ({u.get('name', '?')})", errs)
        if not u.get("type"):
            errs.append(f"units[{i}]: 'type' must be a non-empty list of vehicle types")
    for i, t in enumerate(data.get("threats", [])):
        _latlon(t, f"threats[{i}] ({t.get('name', '?')})", errs)

    group_names = {u["name"] for u in data.get("units", []) if "name" in u}
    group_names |= {s["callsign"] for s in data.get("support", []) if "callsign" in s}

    for i, ph in enumerate(data["storyboard"]):
        where = f"storyboard[{i}] ({ph.get('phase', '?')})"
        if "phase" not in ph or "beat" not in ph:
            errs.append(f"{where}: needs 'phase' and 'beat'")
        for w in ph.get("waypoints", []):
            if w not in wp_names:
                errs.append(f"{where}: unknown waypoint '{w}'")
        trig = ph.get("trigger")
        if not trig:
            continue
        when = trig.get("when") or {}
        if len(when) != 1 or next(iter(when)) not in TRIGGER_WHEN:
            errs.append(f"{where}.trigger.when: must be exactly one of {sorted(TRIGGER_WHEN)}")
        elif "player_in_zone" in when and when["player_in_zone"] not in wp_names:
            errs.append(f"{where}.trigger: player_in_zone references unknown waypoint '{when['player_in_zone']}'")
        elif "group_dead" in when and when["group_dead"] not in group_names:
            errs.append(f"{where}.trigger: group_dead references unknown group '{when['group_dead']}'")
        for g in trig.get("activate", []):
            if g not in group_names:
                errs.append(f"{where}.trigger: activate references unknown group '{g}'")

    if errs:
        raise MissionError("\n".join(errs))
