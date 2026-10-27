"""mission.yaml -> pydcs Mission -> .miz"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import dcs
from dcs import action, condition, task, triggers, weather
from dcs.mission import StartType
from dcs.terrain import Caucasus

from .geo import FT, KTS, NM, point

TARGET_FLAG = 99          # set by either target-destroyed helper rule
DEFAULT_ZONE_KM = 10
START_TYPES = {"cold": StartType.Cold, "warm": StartType.Warm, "runway": StartType.Runway}


def _type(module, name: str):
    try:
        return getattr(module, name)
    except AttributeError:
        raise ValueError(f"unknown unit type '{name}' in {module.__name__}") from None


def _vehicle(name: str):
    for cat in ("AirDefence", "Armor", "Unarmed", "Infantry", "Artillery"):
        t = getattr(getattr(dcs.vehicles, cat), name, None)
        if t is not None:
            return t
    raise ValueError(f"unknown vehicle type '{name}'")


def build(data: dict, out_path: Path, kneeboard_pages: list[Path] = ()) -> dcs.Mission:
    terrain = Caucasus()
    m = dcs.Mission(terrain)
    meta = data["meta"]
    blue = m.country(meta.get("blue_country", "USA"))
    red = m.country(meta.get("red_country", "Russia"))

    d = meta["date"] if isinstance(meta["date"], date) else date.fromisoformat(meta["date"])
    hh, mm = map(int, meta["start_time"].split(":"))
    m.start_time = datetime(d.year, d.month, d.day, hh, mm)

    w = meta.get("weather", {})
    wind = weather.Wind(w.get("wind_from_deg", 0), w.get("wind_kts", 0) * KTS / 3.6)
    m.weather.wind_at_ground = wind
    m.weather.wind_at_2000 = wind
    m.weather.wind_at_8000 = wind
    m.weather.season_temperature = w.get("temperature_c", 15)
    m.weather.qnh = w.get("qnh_inhg", 29.92) * 25.4

    groups: dict[str, object] = {}
    zones: dict[str, object] = {}

    # --- flights ---------------------------------------------------------
    for f in data["flights"]:
        ac = _type(dcs.planes, f["aircraft"])
        airport = _airport(terrain, f["base"])
        fg = m.flight_group_from_airport(
            blue, f["callsign"], ac, airport,
            maintask=task.GroundAttack,
            start_type=START_TYPES[f.get("start", "cold")],
            group_size=f.get("count", 1),
        )
        groups[f["callsign"]] = fg
        if f.get("player"):
            fg.units[0].set_player()
        if "radio1_mhz" in f:
            fg.set_frequency(f["radio1_mhz"])
        for unit in fg.units:
            unit.pylons = {}
            for pylon, weapon in (f.get("loadout") or {}).items():
                unit.load_pylon(getattr(getattr(ac, f"Pylon{pylon}"), weapon))

        for wp in f["waypoints"]:
            pt = point(terrain, wp)
            mp = fg.add_waypoint(pt, wp.get("alt_ft", 20000) * FT, wp.get("kts", 420) * KTS, wp["name"])
            if wp.get("action") == "bomb":
                tgt = point(terrain, data["target"])
                mp.tasks.append(task.Bombing(tgt, weapon_type=task.WeaponType.Guided, group_attack=True))
            zones[wp["name"]] = m.triggers.add_triggerzone(
                pt, radius=wp.get("zone_km", DEFAULT_ZONE_KM) * 1000, name=f"ZONE {wp['name']}")
        if "land" in f:
            fg.land_at(_airport(terrain, f["land"]))

    player_group = next(groups[f["callsign"]] for f in data["flights"] if f.get("player"))

    # --- ground units ----------------------------------------------------
    for u in data.get("units", []):
        country = red if u.get("coalition", "red") == "red" else blue
        vg = m.vehicle_group_platoon(country, u["name"], [_vehicle(t) for t in u["type"]],
                                     point(terrain, u), heading=u.get("heading", 0))
        vg.late_activation = bool(u.get("late_activation"))
        groups[u["name"]] = vg

    # --- support flights -------------------------------------------------
    for s in data.get("support", []):
        country = red if s.get("coalition") == "red" else blue
        ac = _type(dcs.planes, s["aircraft"])
        if s["kind"] == "awacs":
            g = m.awacs_flight(country, s["callsign"], ac, None, point(terrain, s),
                               race_distance=s.get("leg_nm", 30) * NM, heading=s.get("heading", 0),
                               altitude=s.get("alt_ft", 30000) * FT, frequency=s.get("freq_mhz", 251))
        elif s["kind"] == "cap":
            g = m.patrol_flight(country, s["callsign"], ac, _airport(terrain, s["base"]),
                                point(terrain, s["from"]), point(terrain, s["to"]),
                                start_type=StartType.Runway, altitude=s.get("alt_ft", 25000) * FT,
                                group_size=s.get("count", 2))
        elif s["kind"] == "intercept":
            g = m.flight_group_from_airport(country, s["callsign"], ac, _airport(terrain, s["base"]),
                                            maintask=task.Intercept, start_type=StartType.Runway,
                                            group_size=s.get("count", 2))
            mp = g.add_waypoint(point(terrain, data["target"]), 6000, 900)
            mp.tasks.append(task.EngageTargets(max_distance=60_000, targets=[task.Targets.All.Air]))
        else:
            raise ValueError(f"support kind '{s['kind']}' not supported")
        g.late_activation = bool(s.get("late_activation"))
        groups[s["callsign"]] = g

    # --- target-destroyed helpers ---------------------------------------
    tz = m.triggers.add_triggerzone(point(terrain, data["target"]),
                                    radius=data["target"].get("zone_m", 80), name="TARGET BRIDGE")
    helpers = [condition.MapObjectIsDead(tz.id)]
    if "Bridge target" in groups:
        helpers.append(condition.GroupDead(groups["Bridge target"].id))
    for cond in helpers:
        r = triggers.TriggerOnce(comment="target destroyed helper")
        r.add_condition(cond)
        r.add_action(action.SetFlag(TARGET_FLAG))
        m.triggerrules.triggers.append(r)

    # --- storyboard triggers ---------------------------------------------
    for ph in data["storyboard"]:
        trig = ph.get("trigger")
        if not trig:
            continue
        (kind, arg), = trig["when"].items()
        r = triggers.TriggerOnce(comment=ph["phase"])
        if kind == "time_after":
            r.add_condition(condition.TimeAfter(arg))
        elif kind == "player_in_zone":
            r.add_condition(condition.PartOfGroupInZone(player_group.id, zones[arg].id))
        elif kind == "group_dead":
            r.add_condition(condition.GroupDead(groups[arg].id))
        elif kind == "flag":
            r.add_condition(condition.FlagIsTrue(arg))
        elif kind == "target_destroyed":
            r.add_condition(condition.FlagIsTrue(TARGET_FLAG))
        for g in trig.get("activate", []):
            r.add_action(action.ActivateGroup(groups[g].id))
        if "message" in trig:
            r.add_action(action.MessageToCoalition(action.Coalition.Blue, m.string(trig["message"]),
                                                   trig.get("seconds", 10)))
        if "set_flag" in trig:
            r.add_action(action.SetFlag(trig["set_flag"]))
        m.triggerrules.triggers.append(r)

    # --- briefing text ---------------------------------------------------
    n = data["narrative"]
    m.set_sortie_text(f"{meta['title']}: {meta.get('subtitle', '')}".strip(": "))
    m.set_description_text(f"{n['backstory'].strip()}\n\n{n.get('hook', '').strip()}\n\nSITUATION\n{data['situation'].strip()}")
    obj = data["objectives"]
    threats = "\n".join(f"- {t['name']}: {t.get('notes', '')}" for t in data.get("threats", []))
    m.set_description_bluetask_text(
        "OBJECTIVES\n" + "\n".join(f"{k.upper()}: {v}" for k, v in obj.items())
        + f"\n\nROE\n{data.get('roe', '').strip()}\n\nTHREATS\n{threats}")

    player_type = _type(dcs.planes, next(f for f in data["flights"] if f.get("player"))["aircraft"])
    for page in kneeboard_pages:
        m.add_aircraft_kneeboard(player_type, Path(page))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out_path))
    return m


def _airport(terrain, name: str):
    ap = getattr(terrain, name.lower(), None) or terrain.airports.get(name.replace("_", "-"))
    if ap is None:
        for k, v in terrain.airports.items():
            if k.replace("-", "_").replace(" ", "_").lower() == name.lower():
                return v
        raise ValueError(f"unknown airport '{name}' on {terrain.name}")
    return ap
