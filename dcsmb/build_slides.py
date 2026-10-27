"""mission.yaml -> slides.html: a presenter deck for briefing the mission as a story.

Same source as the briefing page. Map slides are inline SVG drawn from the
coastline in dcsmb/data, so the deck works offline (and projects cleanly).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from markupsafe import Markup, escape

from .build_hangar import AIRCRAFT_NAMES
from .build_html import env, view_model

DATA = Path(__file__).resolve().parent / "data"
W, H = 900, 640  # map viewBox


# --- SVG maps -------------------------------------------------------------

class Projection:
    """Equirectangular fit of a lat/lon box into the W x H viewBox."""

    def __init__(self, pts: list[tuple[float, float]], pad: float = 0.25, min_span_km: float = 25):
        lats, lons = [p[0] for p in pts], [p[1] for p in pts]
        self.k = math.cos(math.radians(sum(lats) / len(lats)))
        cx, cy = (min(lons) + max(lons)) / 2, (min(lats) + max(lats)) / 2
        span_x = max((max(lons) - min(lons)) * self.k, min_span_km / 111)
        span_y = max(max(lats) - min(lats), min_span_km / 111)
        self.scale = min(W / (span_x * (1 + 2 * pad)), H / (span_y * (1 + 2 * pad)))
        self.cx, self.cy = cx, cy

    def __call__(self, lat: float, lon: float) -> tuple[float, float]:
        return (W / 2 + (lon - self.cx) * self.k * self.scale, H / 2 - (lat - self.cy) * self.scale)

    def km(self, km: float) -> float:
        return km / 111 * self.scale


def _coast(theater: str) -> list[list[list[float]]]:
    path = DATA / f"coast_{theater}.json"
    return json.loads(path.read_text()) if path.exists() else []


class Labels:
    """Places point labels so they don't overlap each other or the map edge.

    Tries right, left, above and below the point; falls back to the right side.
    Labels are added in priority order (route first) and drawn last, on top.
    """
    CHAR_W, LINE_H = 10.4, 18

    def __init__(self):
        self.items: list[tuple] = []

    def add(self, x: float, y: float, text: str, cls: str) -> str:
        self.items.append((x, y, text, cls))
        return ""

    def render(self) -> str:
        placed, out = [], []
        for x, y, text, cls in self.items:
            w = self.CHAR_W * len(text)
            for dx, dy, anchor in ((12, 5, "start"), (-12, 5, "end"), (-w / 2, -14, "start"), (-w / 2, 26, "start"),
                                   (12, -14, "start"), (12, 24, "start"), (-12, -14, "end"), (-12, 24, "end")):
                left = x + dx - (w if anchor == "end" else 0)
                box = (left, y + dy - self.LINE_H + 4, left + w, y + dy + 4)
                inside = box[0] >= 2 and box[2] <= W - 2 and box[1] >= 2 and box[3] <= H - 2
                if inside and not any(b[0] < box[2] and box[0] < b[2] and b[1] < box[3] and box[1] < b[3] for b in placed):
                    break
            else:
                dx, dy, anchor = (12, 5, "start") if x < W - w - 30 else (-12, 5, "end")
                left = x + dx - (w if anchor == "end" else 0)
                box = (left, y + dy - self.LINE_H + 4, left + w, y + dy + 4)
            placed.append(box)
            a = ' text-anchor="end"' if anchor == "end" else ""
            out.append(f'<text class="{cls}" x="{x + dx:.1f}" y="{y + dy:.1f}"{a}>{escape(text)}</text>')
        return "".join(out)


def svg_map(vm: dict, focus: list[str] | None = None, show_rings: bool = True) -> Markup:
    """Route, threats, support and target. `focus` waypoint names get highlighted and framed."""
    route = vm["route"]
    names = [p["name"] for p in route]
    if focus:
        i0 = max(0, names.index(focus[0]) - 1)
        i1 = names.index(focus[-1])
        hl = route[i0:i1 + 1]
        frame = [(p["lat"], p["lon"]) for p in hl]
        pr = Projection(frame, pad=0.35)
    else:
        hl = []
        frame = [(p["lat"], p["lon"]) for p in route]
        for t in vm.get("threats", []):  # keep whole threat rings in frame
            dlat = t.get("range_km", 0) / 111
            dlon = dlat / math.cos(math.radians(t["lat"]))
            frame += [(t["lat"] + dlat, t["lon"]), (t["lat"] - dlat, t["lon"]), (t["lat"], t["lon"] - dlon), (t["lat"], t["lon"] + dlon)]
        pr = Projection(frame, pad=0.1)

    labels = Labels()
    out = [f'<svg viewBox="0 0 {W} {H}" class="map" role="img" aria-label="Mission map">',
           '<rect class="sea" width="100%" height="100%"/>']

    # lat/lon grid every 0.5 deg (or 0.1 when zoomed in)
    step = 0.1 if pr.scale > 4000 else 0.5
    lat0, lat1 = pr.cy - H / 2 / pr.scale, pr.cy + H / 2 / pr.scale
    lon0, lon1 = pr.cx - W / 2 / pr.scale / pr.k, pr.cx + W / 2 / pr.scale / pr.k
    g = math.floor(lat0 / step) * step
    while g <= lat1:
        y = pr(g, pr.cx)[1]
        out.append(f'<line class="grid" x1="0" x2="{W}" y1="{y:.1f}" y2="{y:.1f}"/>'
                   f'<text class="gridlbl" x="6" y="{y - 4:.1f}">{g:.1f}N</text>')
        g += step
    g = math.floor(lon0 / step) * step
    while g <= lon1:
        x = pr(pr.cy, g)[0]
        out.append(f'<line class="grid" y1="0" y2="{H}" x1="{x:.1f}" x2="{x:.1f}"/>'
                   f'<text class="gridlbl" x="{x + 4:.1f}" y="{H - 8}">{g:.1f}E</text>')
        g += step

    for line in _coast(vm["meta"]["theater"]):
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pr(a, b) for a, b in line))
        out.append(f'<polyline class="coast" points="{pts}"/>')

    if show_rings:
        for t in vm.get("threats", []):
            x, y = pr(t["lat"], t["lon"])
            if t.get("range_km"):
                out.append(f'<circle class="ring {t["kind"]}" cx="{x:.1f}" cy="{y:.1f}" r="{pr.km(t["range_km"]):.1f}"/>')
            out.append(f'<circle class="threat {t["kind"]}" cx="{x:.1f}" cy="{y:.1f}" r="6"/>'
                       + labels.add(x, y, t["name"].split(" (")[0], f"lbl {t['kind']}"))

    for s in vm.get("support", []):
        if s.get("from") and s.get("to"):
            (x1, y1), (x2, y2) = pr(s["from"]["lat"], s["from"]["lon"]), pr(s["to"]["lat"], s["to"]["lon"])
            out.append(f'<line class="cap" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"/>'
                       + labels.add(x2, y2, f'{s["callsign"]} CAP', "lbl friendly"))
        elif "lat" in s:
            x, y = pr(s["lat"], s["lon"])
            out.append(f'<circle class="friendly-dot" cx="{x:.1f}" cy="{y:.1f}" r="6"/>'
                       + labels.add(x, y, s["callsign"], "lbl friendly"))

    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pr(p["lat"], p["lon"]) for p in route))
    out.append(f'<polyline class="route{" dim" if hl else ""}" points="{pts}"/>')
    if hl:
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pr(p["lat"], p["lon"]) for p in hl))
        out.append(f'<polyline class="route hl" points="{pts}"/>')

    tx, ty = pr(vm["target"]["lat"], vm["target"]["lon"])
    out.append(f'<g class="target" transform="translate({tx:.1f},{ty:.1f})"><circle r="13"/>'
               '<path d="M0 -20v12M0 8v12M-20 0h12M8 0h12"/></g>')

    drawn = set()
    for p in route:
        x, y = pr(p["lat"], p["lon"])
        if not (-50 < x < W + 50 and -50 < y < H + 50) or p["name"] in drawn:
            continue
        drawn.add(p["name"])  # the home base is both the first and last route point
        label = f'{p["num"]} {p["name"]}' if p["kind"] == "wp" else p["name"]
        cls = "wp on" if p["name"] in (focus or []) else "wp"
        out.append(f'<circle class="{cls}" cx="{x:.1f}" cy="{y:.1f}" r="{8 if p["kind"] == "base" else 6}"/>'
                   + labels.add(x, y, label, "lbl"))

    # route labels get first pick of the space, then threats and support
    route_lbls = [it for it in labels.items if it[3] == "lbl"]
    labels.items = route_lbls + [it for it in labels.items if it[3] != "lbl"]
    out.append(labels.render())
    out.append("</svg>")
    return Markup("".join(out))


# --- Deck -----------------------------------------------------------------

def _trigger_note(t: dict) -> str:
    (k, v), = t["when"].items()
    when = {"time_after": f"{v}s after mission start", "player_in_zone": f"when the flight enters the {v} zone",
            "group_dead": f"when {v} is destroyed", "flag": f"when flag {v} is set",
            "target_destroyed": "when the target is destroyed"}[k]
    parts = [f"In the sim this fires {when}."]
    if t.get("activate"):
        parts.append(f"It activates {', '.join(t['activate'])}.")
    return " ".join(parts)


def slides(data: dict) -> list[dict]:
    vm = view_model(data)
    n, meta, player = data["narrative"], data["meta"], vm["player"]
    ac = AIRCRAFT_NAMES.get(player["aircraft"], player["aircraft"])
    deck: list[dict] = []
    add = lambda kind, **kw: deck.append({"kind": kind, **kw})

    add("title", eyebrow=f"Operation {n['operation']}", title=meta.get("subtitle") or meta["title"],
        sub=f"{meta['date']} · Step {meta['start_time']}L · {player['callsign']} · {player.get('count', 1)}× {ac}",
        quote=(n.get("hook") or "").strip(),
        notes="Set the tone. Read the quote out loud, then go straight into the story.")

    paras = [p.strip() for p in n["backstory"].strip().split("\n\n") if p.strip()]
    for i, p in enumerate(paras):
        add("story", eyebrow="The story so far" if i == 0 else "Why it matters", text=p,
            notes="Tell it, don't read it. One idea per slide.")

    add("cast", eyebrow="Who's who", entries=n.get("characters", []),
        notes="These are the voices pilots will hear on the radio during the mission.")

    add("map", eyebrow="Situation", title="The battlespace", text=data["situation"].strip(),
        svg=svg_map(vm), notes="Walk the route from base to target and back. Point out the threat rings.")

    add("objectives", eyebrow="Tasking", title="Objectives", entries=list(data["objectives"].items()),
        notes="Primary is what wins the mission. Everything else is a bonus or a way home.")

    tgt = data["target"]
    tgt_wp = next((w["name"] for w in player["waypoints"] if w.get("action") == "bomb"), None)
    add("map", eyebrow="Target", title=tgt["name"],
        text=f"{tgt.get('description', '')}\n\nDMPI: {tgt.get('dmpi', '')}",
        svg=svg_map(vm, focus=[tgt_wp] if tgt_wp else None),
        notes=f"Target coordinates {tgt['lat']:.4f}N {tgt['lon']:.4f}E. Laser code "
              f"{'/'.join(map(str, player.get('laser_codes', []))) or 'n/a'}.")

    add("threats", eyebrow="Threats", title="What's waiting for you", entries=data.get("threats", []),
        notes="Emphasise how each threat is triggered. This is where the story turns.")

    support = [f"{s['callsign']}: {s.get('count', 1)}× {AIRCRAFT_NAMES.get(s['aircraft'], s['aircraft'])}"
               f" ({s['kind'].upper()}{', red' if s.get('coalition') == 'red' else ''})" for s in data.get("support", [])]
    add("package", eyebrow="Package", title=f"{player['callsign']} flight",
        rows=[("Aircraft", f"{player.get('count', 1)}× {ac}"), ("Start", f"{player.get('start', 'cold').title()} start, {vm['route'][0]['name']}"),
              ("Loadout", player.get("loadout_summary", "")), ("Joker / Bingo", f"{player.get('joker_lbs', '?')} / {player.get('bingo_lbs', '?')} lb")],
        support=[s for s in support if "red" not in s],
        notes="Confirm everyone has the loadout before step.")

    add("divider", eyebrow="The plan", title="How it plays out",
        notes="Each phase slide pairs the story beat with the radio call players will hear.")
    for i, ph in enumerate(data["storyboard"], 1):
        t = ph.get("trigger") or {}
        add("phase", eyebrow=f"Phase {i} · {ph.get('time', '')}", title=ph["phase"], text=ph["beat"].strip(),
            radio=t.get("message"), svg=svg_map(vm, focus=ph["waypoints"]) if ph.get("waypoints") else None,
            notes=" ".join(x for x in [ph.get("notes", ""), _trigger_note(t) if t else ""] if x))

    add("comms", eyebrow="Comms", title="Frequencies", entries=data.get("comms", []),
        notes="Kneeboard page 2 carries this card in the cockpit.")
    w = meta.get("weather", {})
    add("package", eyebrow="Conditions", title="Weather & ROE",
        rows=[("Wind", f"{w.get('wind_from_deg', 0):03d}° / {w.get('wind_kts', 0)} kt"), ("Clouds", w.get("clouds", "")),
              ("Visibility", w.get("visibility", "")), ("Temp / QNH", f"{w.get('temperature_c', '')} °C / {w.get('qnh_inhg', '')} inHg"),
              ("ROE", data.get("roe", "").strip())], support=[], notes="")
    add("title", eyebrow=f"Operation {n['operation']}", title="Questions?",
        sub=f"Step {meta['start_time']}L", quote="", notes="Stop here before the flight. The slides after this are for the debrief.")

    add("divider", eyebrow="After the mission", title="Debrief", notes="Show the outcome that matches what happened.")
    labels = {"success": "Mission success", "partial": "Partial success", "failure": "Mission failed"}
    for k in ("success", "partial", "failure"):
        if n.get("outcomes", {}).get(k):
            add("outcome", eyebrow="Debrief", title=labels[k], tone=k, text=n["outcomes"][k].strip(), notes="")
    return deck


def build(data: dict, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(env().get_template("slides.html.j2").render(meta=data["meta"], narrative=data["narrative"], slides=slides(data)))
    return out_path
