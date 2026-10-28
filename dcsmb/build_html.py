"""mission.yaml -> briefing.html (map, storyboard, briefing cards, narrative)."""
from __future__ import annotations

import json
import math
from pathlib import Path

from dcs.terrain import Caucasus
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from .build_miz import _airport

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
# What each cockpit calls its radios, for the comms card ("COMM2 · CH 2")
RADIO_NAMES = {"FA_18C_hornet": {1: "COMM1", 2: "COMM2"}, "F_16C_50": {1: "UHF", 2: "VHF"},
               "A_10C_2": {1: "ARC-210", 2: "UHF", 3: "FM"}, "F_14B": {1: "UHF (pilot)", 2: "V/UHF (RIO)"},
               "AV8BNA": {1: "COMM1", 2: "COMM2"}}

# Headings that differ between a combat mission and a training event (same YAML keys underneath)
LABELS = {
    "operational": {"eyebrow": "Operation", "story": "The story so far", "story_more": "Why it matters", "cast": "Cast",
                    "situation": "Situation", "objectives": "Objectives", "roe": "Rules of engagement",
                    "threats": "Threats", "threats_title": "What's waiting for you", "target": "Target",
                    "plan": "Storyboard & flight plan", "battlespace": "The battlespace", "nav_story": "Story",
                    "divider": "How it plays out",
                    "outcomes": {"success": "Success", "partial": "Partial", "failure": "Failure"}},
    "training": {"eyebrow": "Training event", "story": "Why we're flying this", "story_more": "Where it fits", "cast": "Instructors and players",
                 "situation": "Event overview", "objectives": "Learning objectives", "roe": "Range and weapons clearance",
                 "threats": "Range players and hazards", "threats_title": "Who and what is out there", "target": "Range target",
                 "plan": "Event flow & flight plan", "battlespace": "The training area", "nav_story": "Overview",
                 "divider": "Event flow",
                 "outcomes": {"success": "Complete", "partial": "Partial: re-fly items", "failure": "Incomplete: re-fly"}},
}


def env() -> Environment:
    e = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    e.filters["paras"] = lambda s: [p.strip() for p in str(s or "").split("\n\n") if p.strip()]
    e.filters["script_json"] = script_json
    return e


def script_json(s: str) -> Markup:
    """JSON text made safe inside <script>: a '</script>' or '<!--' in any YAML string can't end the block."""
    for ch, esc in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"), ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        s = s.replace(ch, esc)
    return Markup(s)


def _ll(airport) -> dict:
    ll = airport.position.latlng()
    return {"name": airport.name, "lat": ll.lat, "lon": ll.lng}


def _offset(lat: float, lon: float, heading: float, nm: float) -> dict:
    """Point `nm` nautical miles from lat/lon along `heading` (flat-earth; fine for orbit legs)."""
    d = nm * 1.852 / 111.0
    return {"lat": lat + d * math.cos(math.radians(heading)),
            "lon": lon + d * math.sin(math.radians(heading)) / math.cos(math.radians(lat))}


def _km(a: dict, b: dict) -> float:
    la1, la2 = math.radians(a["lat"]), math.radians(b["lat"])
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(math.radians(b["lon"] - a["lon"]) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def _place(name: str, terrain, ships: dict, at_end: bool = False) -> dict:
    """An airfield or a ship group, as a map point. Ships move: `at_end` gives where it will be at recovery."""
    if name in ships:
        sh = ships[name]
        p = (sh.get("route") or [sh])[-1] if at_end else sh
        return {"name": f"{name} (recovery)" if at_end else name, "lat": p["lat"], "lon": p["lon"], "ship": True}
    return _ll(_airport(terrain, name))


def profile_svg(route: list[dict], dark: bool = False) -> Markup:
    """Planned altitude along the route. Terrain-following (AGL) legs are drawn dashed."""
    W, H, L, R, T, B = 900, 240, 56, 16, 40, 44
    dist, total = [0.0], 0.0
    for a, b in zip(route, route[1:]):
        total += _km(a, b)
        dist.append(total)
    top = max(30000, max(p.get("alt_ft", 0) for p in route))
    x = lambda d: L + (W - L - R) * d / (total or 1)
    y = lambda ft: H - B - (H - B - T) * ft / top
    out = [f'<svg viewBox="0 0 {W} {H}" class="profile" role="img" aria-label="Planned altitude profile">']
    for ft in range(0, int(top) + 1, 10000):
        out.append(f'<line class="pgrid" x1="{L}" x2="{W - R}" y1="{y(ft):.1f}" y2="{y(ft):.1f}"/>'
                   f'<text class="paxis" x="{L - 8}" y="{y(ft) + 4:.1f}" text-anchor="end">{ft // 1000}k</text>')
    out.append(f'<text class="paxis" x="{L}" y="{T - 24}">Route length {total:.0f} km</text>')
    for i, (a, b) in enumerate(zip(route, route[1:])):
        agl = a.get("agl") and b.get("agl")
        out.append(f'<line class="pleg{" agl" if agl else ""}" x1="{x(dist[i]):.1f}" y1="{y(a.get("alt_ft", 0)):.1f}" '
                   f'x2="{x(dist[i + 1]):.1f}" y2="{y(b.get("alt_ft", 0)):.1f}"/>')
    # Close waypoints get their labels stacked into rows instead of overprinting each other
    name_rows: list[float] = []   # right edge of the last label in each row above the line
    sub_rows: list[float] = []
    def row(rows: list[float], left: float, right: float) -> int:
        for i, edge in enumerate(rows):
            if left > edge + 6:
                rows[i] = right
                return i
        rows.append(right)
        return len(rows) - 1
    for p, d in zip(route, dist):
        alt, px = p.get("alt_ft", 0), x(d)
        label = p["name"] if p["kind"] == "base" else f'{p["num"]} {p["name"]}'
        sub = "" if p["kind"] == "base" else f'{alt / 1000:g}k{" AGL" if p.get("agl") else ""}'
        half = 3.6 * len(label)
        lx = min(max(px, L + half), W - R - half)  # keep labels inside the chart
        r = row(name_rows, lx - half, lx + half)
        out.append(f'<circle class="pwp{" agl" if p.get("agl") else ""}" cx="{px:.1f}" cy="{y(alt):.1f}" r="4"/>')
        out.append(f'<text class="plbl" x="{lx:.1f}" y="{y(alt) - 10 - 14 * r:.1f}" text-anchor="middle">{escape(label)}</text>')
        if sub:
            half = 3.4 * len(sub)
            r = row(sub_rows, px - half, px + half)
            out.append(f'<text class="psub" x="{px:.1f}" y="{H - 20 + 12 * r}" text-anchor="middle">{sub}</text>')
    out.append("</svg>")
    return Markup("".join(out))


def view_model(data: dict, audience: str = "pilot") -> dict:
    """Everything the templates need, with airfields and ships resolved to coordinates.

    audience="pilot" leaves out anything the squadron wouldn't know at brief time
    (red flights and red ships); the director view keeps everything.
    """
    terrain = Caucasus()
    training = data["meta"].get("category") == "training"
    ships = {sh["name"]: sh for sh in data.get("ships", [])}
    player = next(f for f in data["flights"] if f.get("player"))
    base = _place(player["base"], terrain, ships)
    land = _place(player.get("land", player["base"]), terrain, ships, at_end=True)
    airfields = {p["name"]: p for p in (base, land) if not p.get("ship")}
    support = []
    for s in data.get("support", []):
        if audience == "pilot" and s.get("coalition") == "red" and not training:
            continue  # training briefs the adversaries; combat missions don't know them
        s = dict(s)
        if "base" in s:
            ap = _place(s["base"], terrain, ships)
            if not ap.get("ship"):
                airfields[ap["name"]] = ap
            s["base_ll"] = ap
        if s["kind"] in ("awacs", "tanker") and "lat" in s:
            s["track_to"] = _offset(s["lat"], s["lon"], s.get("heading", 0), s.get("leg_nm", 30))
        support.append(s)
    ship_list = [sh for sh in data.get("ships", []) if audience != "pilot" or sh.get("coalition", "blue") == "blue"]

    route = [{"name": base["name"], "lat": base["lat"], "lon": base["lon"], "kind": "base", "alt_ft": 0, "ship": base.get("ship", False)}]
    route += [dict(wp, kind="wp", num=i + 1) for i, wp in enumerate(player["waypoints"])]
    route.append({"name": land["name"], "lat": land["lat"], "lon": land["lon"], "kind": "base", "alt_ft": 0})

    target = data["target"]
    if audience == "pilot":  # trigger plumbing names the real (possibly hidden) groups
        target = {k: v for k, v in target.items() if k not in ("groups", "kill_pct", "zone_m")}
    map_data = {
        "route": route,
        "target": target,
        "threats": data.get("threats", []),
        "support": support,
        "ships": [{"name": sh["name"], "lat": sh["lat"], "lon": sh["lon"], "route": sh.get("route", []),
                   "coalition": sh.get("coalition", "blue")} for sh in ship_list],
        "airfields": list(airfields.values()),
        "phases": [{"phase": p["phase"], "waypoints": p.get("waypoints", [])} for p in data["storyboard"]],
    }
    from .build_hangar import AIRCRAFT_NAMES
    radios = RADIO_NAMES.get(player["aircraft"], {})
    comms = [{**c, "preset": f"{radios.get(c['radio'], 'Radio ' + str(c['radio']))} · CH {c['channel']}" if "radio" in c else "Manual / listen"}
             for c in data.get("comms", [])]
    navaids = [f"{sh['name']}: TACAN {sh['tacan']['channel']} ({sh['tacan'].get('callsign', '')})"
               + (f", ICLS {sh['icls']}" if "icls" in sh else "") for sh in ship_list if "tacan" in sh]
    navaids += [f"{s['callsign']} ({s['kind']}): TACAN {s['tacan']['channel']}, {s.get('alt_ft', 0):,} ft, {s.get('kts', '')} kt"
                for s in support if s["kind"] == "tanker" and "tacan" in s]
    return {**data, "comms": comms, "training": data.get("training", {}), "is_training": training,
            "T": LABELS["training" if training else "operational"], "player": player, "route": route, "support": support, "target": target,
            "ships": ship_list, "navaids": navaids,
            "aircraft_name": AIRCRAFT_NAMES.get(player["aircraft"], player["aircraft"].replace("_", " ")),
            "profile": profile_svg(route), "map_json": json.dumps(map_data)}


def build(data: dict, out_path: Path) -> Path:
    vm = view_model(data)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(env().get_template("briefing.html.j2").render(**vm))
    return out_path
