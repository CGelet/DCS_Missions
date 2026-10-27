"""mission.yaml -> briefing.html (map, storyboard, briefing cards, narrative)."""
from __future__ import annotations

import json
from pathlib import Path

from dcs.terrain import Caucasus
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .build_miz import _airport

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


def env() -> Environment:
    e = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    e.filters["paras"] = lambda s: [p.strip() for p in str(s or "").split("\n\n") if p.strip()]
    return e


def _ll(airport) -> dict:
    ll = airport.position.latlng()
    return {"name": airport.name, "lat": ll.lat, "lon": ll.lng}


def view_model(data: dict, audience: str = "pilot") -> dict:
    """Everything the templates need, with airfield names resolved to coordinates.

    audience="pilot" leaves out anything the squadron wouldn't know at brief time
    (red flights in `support`); the director view keeps everything.
    """
    terrain = Caucasus()
    player = next(f for f in data["flights"] if f.get("player"))
    base = _ll(_airport(terrain, player["base"]))
    land = _ll(_airport(terrain, player.get("land", player["base"])))
    airfields = {base["name"]: base, land["name"]: land}
    support = []
    for s in data.get("support", []):
        if audience == "pilot" and s.get("coalition") == "red":
            continue
        s = dict(s)
        if "base" in s:
            ap = _ll(_airport(terrain, s["base"]))
            airfields[ap["name"]] = ap
            s["base_ll"] = ap
        support.append(s)

    route = [{"name": base["name"], "lat": base["lat"], "lon": base["lon"], "kind": "base"}]
    route += [dict(wp, kind="wp", num=i + 1) for i, wp in enumerate(player["waypoints"])]
    route.append({"name": land["name"], "lat": land["lat"], "lon": land["lon"], "kind": "base"})

    target = data["target"]
    if audience == "pilot":  # trigger plumbing names the real (possibly hidden) groups
        target = {k: v for k, v in target.items() if k not in ("groups", "kill_pct", "zone_m")}
    map_data = {
        "route": route,
        "target": target,
        "threats": data.get("threats", []),
        "support": support,
        "airfields": list(airfields.values()),
        "phases": [{"phase": p["phase"], "waypoints": p.get("waypoints", [])} for p in data["storyboard"]],
    }
    from .build_hangar import AIRCRAFT_NAMES
    return {**data, "player": player, "route": route, "support": support, "target": target,
            "aircraft_name": AIRCRAFT_NAMES.get(player["aircraft"], player["aircraft"].replace("_", " ")),
            "map_json": json.dumps(map_data)}


def build(data: dict, out_path: Path) -> Path:
    vm = view_model(data)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(env().get_template("briefing.html.j2").render(**vm))
    return out_path
