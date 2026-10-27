"""mission.yaml -> director.html: the spoiler view for whoever runs or debriefs the mission.

Shows what the pilots were told next to what is really there, every random roll and its odds,
the full trigger script with radio calls, and the debrief outcomes.
"""
from __future__ import annotations

import json
from pathlib import Path

from .build_html import env, view_model
from .schema import phase_triggers


def describe_when(when: dict) -> str:
    parts = []
    for k, v in when.items():
        parts.append({
            "time_after": lambda: f"{v} s after mission start",
            "player_in_zone": lambda: f"player flight enters the {v} zone",
            "group_dead": lambda: f"{v} is destroyed",
            "flag": lambda: f"flag {v} is set",
            "target_destroyed": lambda: "the target is destroyed",
            "variant": lambda: f"“{v[0]}” rolled option {v[1]}",
        }[k]())
    return " and ".join(parts) or "mission start"


def view(data: dict) -> dict:
    vm = view_model(data, audience="director")
    activations: dict[str, list[str]] = {}
    rolls = []

    for v in data.get("variants", []):
        n = len(v["options"])
        rolls.append({"what": f"Variant “{v['name']}”", "odds": [
            (o.get("label", f"Option {i}"), round(100 / n)) for i, o in enumerate(v["options"], 1)]})
        for i, o in enumerate(v["options"], 1):
            when = f", once {describe_when(o['when'])}" if o.get("when") else " at mission start"
            for g in o.get("activate", []):
                activations.setdefault(g, []).append(f"{round(100 / n)}%: variant “{v['name']}” option {i} ({o.get('label', i)}){when}")

    script = []
    for ph in data["storyboard"]:
        trigs = []
        for t in phase_triggers(ph):
            trigs.append({**t, "when_text": describe_when(t["when"])})
            if "chance" in t:
                rolls.append({"what": f"{ph['phase']}: " + (", ".join(t.get("activate", [])) or "event"),
                              "odds": [("Happens", t["chance"]), ("Never happens", 100 - t["chance"])]})
            for g in t.get("activate", []):
                odds = f"{t['chance']}%" if "chance" in t else "Always"
                activations.setdefault(g, []).append(f"{odds}: when {describe_when(t['when'])} ({ph['phase']})")
        script.append({**ph, "trigger_list": trigs})

    briefed = {t["name"] for t in data.get("threats", [])}
    units = []
    for u in data.get("units", []):
        src = activations.get(u["name"]) or (["Active from mission start"] if not u.get("late_activation")
                                              else ["Never activated (check the YAML)"])
        units.append({**u, "activation": src, "types": _summarise(u["type"])})

    for s in vm["support"]:
        s["activation"] = activations.get(s["callsign"]) or (["Active from mission start"] if not s.get("late_activation")
                                                             else ["Never activated (check the YAML)"])

    map_data = json.loads(vm["map_json"])
    map_data["units"] = [{"name": u["name"], "lat": u["lat"], "lon": u["lon"], "coalition": u.get("coalition", "red"),
                          "route": u.get("route", []), "late": bool(u.get("late_activation"))} for u in data.get("units", [])]
    return {**vm, "units_truth": units, "rolls": rolls, "script": script, "briefed": briefed,
            "map_json": json.dumps(map_data)}


def _summarise(types: list[str]) -> str:
    counts: dict[str, int] = {}
    for t in types:
        counts[t] = counts.get(t, 0) + 1
    return ", ".join(f"{n}× {t.replace('_', ' ')}" for t, n in counts.items())


def build(data: dict, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(env().get_template("director.html.j2").render(**view(data), describe_when=describe_when))
    return out_path
