"""mission.yaml -> pydcs Mission -> .miz"""
from __future__ import annotations

import random
import zipfile
from datetime import date, datetime
from pathlib import Path

import dcs
from dcs import action, condition, task, triggers, weather
from dcs.mission import StartType
from dcs.point import PointAction
from dcs.terrain import Caucasus

from .geo import FT, KTS, NM, point
from .schema import phase_triggers

TARGET_FLAG = 99          # set by any target-destroyed helper rule
CHANCE_FLAG_BASE = 200    # one flag per `chance` trigger, rolled at mission start
VARIANT_FLAG_BASE = 300   # default flag for variants without an explicit one
DEFAULT_ZONE_KM = 10
START_TYPES = {"cold": StartType.Cold, "warm": StartType.Warm, "runway": StartType.Runway}
MAINTASKS = {"bomb": task.GroundAttack, "sead": task.SEAD, "cas": task.CAS}


def _type(module, name: str):
    try:
        return getattr(module, name)
    except AttributeError:
        raise ValueError(f"unknown unit type '{name}' in {module.__name__}") from None


def _weapon(ac, pylon: int, name: str):
    station = getattr(ac, f"Pylon{pylon}", None)
    if station is None:
        raise ValueError(f"{ac.__name__} has no pylon {pylon}")
    if not hasattr(station, name):
        close = sorted(a for a in dir(station) if not a.startswith("_") and name.split("_")[0].lower() in a.lower())
        raise ValueError(f"{ac.__name__} pylon {pylon} has no weapon '{name}'. Similar names: {close[:8] or 'none'}")
    return getattr(station, name)


def _vehicle(name: str):
    for cat in ("AirDefence", "Armor", "Unarmed", "Infantry", "Artillery"):
        t = getattr(getattr(dcs.vehicles, cat), name, None)
        if t is not None:
            return t
    raise ValueError(f"unknown vehicle type '{name}'")


def build(data: dict, out_path: Path, kneeboard_pages: list[Path] = ()) -> dcs.Mission:
    meta = data["meta"]
    random.seed(meta["id"])  # pydcs randomises tail numbers; keep rebuilds byte-identical
    terrain = Caucasus()
    m = dcs.Mission(terrain)
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
        actions = {wp.get("action") for wp in f["waypoints"]}
        maintask = next((t for a, t in MAINTASKS.items() if a in actions), task.GroundAttack)
        fg = m.flight_group_from_airport(
            blue, f["callsign"], ac, airport,
            maintask=maintask,
            start_type=START_TYPES[f.get("start", "cold")],
            group_size=f.get("count", 1),
        )
        groups[f["callsign"]] = fg
        _set_callsign(fg, f["callsign"], blue, ac)
        if f.get("player"):
            fg.units[0].set_player()
            _set_presets(fg, data.get("comms", []))
        if "radio1_mhz" in f:
            fg.set_frequency(f["radio1_mhz"])
        for unit in fg.units:
            unit.pylons = {}
            for pylon, weapon in (f.get("loadout") or {}).items():
                unit.load_pylon(_weapon(ac, pylon, weapon))

        for wp in f["waypoints"]:
            pt = point(terrain, wp)
            mp = fg.add_waypoint(pt, wp.get("alt_ft", 20000) * FT, wp.get("kts", 420) * KTS, wp["name"])
            # Tasks steer the AI wingman; the player flies their own plan.
            if wp.get("action") == "bomb":
                tgt = point(terrain, data["target"])
                mp.tasks.append(task.Bombing(tgt, weapon_type=task.WeaponType.Guided, group_attack=True))
            elif wp.get("action") == "sead":
                mp.tasks.append(task.EngageTargets(max_distance=80_000, targets=[task.Targets.All.GroundUnits.AirDefence]))
            elif wp.get("action") == "cas":
                mp.tasks.append(task.EngageTargets(max_distance=15_000, targets=[task.Targets.All.GroundUnits]))
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
        for p in u.get("route", []):
            vg.add_waypoint(point(terrain, p), PointAction.OnRoad if u.get("on_road", True) else PointAction.OffRoad,
                            u.get("speed_kmh", 25))
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
            if "freq_mhz" in s:
                g.set_frequency(s["freq_mhz"])
        elif s["kind"] == "intercept":
            g = m.flight_group_from_airport(country, s["callsign"], ac, _airport(terrain, s["base"]),
                                            maintask=task.Intercept, start_type=StartType.Runway,
                                            group_size=s.get("count", 2))
            mp = g.add_waypoint(point(terrain, data["target"]), 6000, 900)
            mp.tasks.append(task.EngageTargets(max_distance=60_000, targets=[task.Targets.All.Air]))
        else:
            raise ValueError(f"support kind '{s['kind']}' not supported")
        g.late_activation = bool(s.get("late_activation"))
        _set_callsign(g, s["callsign"], country, ac, awacs=s["kind"] == "awacs")
        groups[s["callsign"]] = g

    # --- random variants (rolled once at mission start) ---------------
    variant_of: dict[str, tuple[int, int]] = {}  # group -> (flag, option number) that activates it
    variant_flags = {v["name"]: v.get("flag", VARIANT_FLAG_BASE + i) for i, v in enumerate(data.get("variants", []))}
    ctx = (player_group, zones, groups, variant_flags)
    for v in data.get("variants", []):
        flag = variant_flags[v["name"]]
        roll = triggers.TriggerStart(comment=f"variant: {v['name']}")
        roll.add_action(action.SetFlagRandom(flag, 1, len(v["options"])))
        m.triggerrules.triggers.append(roll)
        for n_opt, o in enumerate(v["options"], 1):
            r = triggers.TriggerOnce(comment=f"variant: {v['name']} = {o.get('label', n_opt)}")
            r.add_condition(condition.FlagEquals(flag, n_opt))
            for c in _when(o.get("when", {}), *ctx):
                r.add_condition(c)
            _actions(m, r, o, groups)
            m.triggerrules.triggers.append(r)
            for g in o.get("activate", []):
                variant_of[g] = (flag, n_opt)

    # --- target-destroyed helpers ---------------------------------------
    tgt = data["target"]
    helpers = []
    if tgt.get("zone_m"):
        tz = m.triggers.add_triggerzone(point(terrain, tgt), radius=tgt["zone_m"], name="TARGET ZONE")
        helpers.append([condition.MapObjectIsDead(tz.id)])
    kill = tgt.get("kill_pct", 100)
    for g in tgt.get("groups", []):
        gid = groups[g].id
        conds = [condition.GroupDead(gid) if kill == 100 else condition.GroupLifeLess(gid, 100 - kill)]
        if g in variant_of:  # only the variant that actually spawned counts
            conds.append(condition.FlagEquals(*variant_of[g]))
        helpers.append(conds)
    for conds in helpers:
        r = triggers.TriggerOnce(comment="target destroyed helper")
        for c in conds:
            r.add_condition(c)
        r.add_action(action.SetFlag(TARGET_FLAG))
        m.triggerrules.triggers.append(r)

    # --- storyboard triggers ---------------------------------------------
    chance_flag = CHANCE_FLAG_BASE
    for ph in data["storyboard"]:
        for trig in phase_triggers(ph):
            r = triggers.TriggerOnce(comment=ph["phase"])
            for c in _when(trig["when"], *ctx):
                r.add_condition(c)
            if "chance" in trig:
                chance_flag += 1
                roll = triggers.TriggerStart(comment=f"{ph['phase']}: {trig['chance']}% roll")
                roll.add_condition(condition.Random(trig["chance"]))
                roll.add_action(action.SetFlag(chance_flag))
                m.triggerrules.triggers.append(roll)
                r.add_condition(condition.FlagIsTrue(chance_flag))
            _actions(m, r, trig, groups)
            m.triggerrules.triggers.append(r)

    # --- briefing text ---------------------------------------------------
    n = data["narrative"]
    m.set_sortie_text(f"{meta['title']}: {meta.get('subtitle', '')}".strip(": "))
    m.set_description_text(f"{n['backstory'].strip()}\n\n{n.get('hook', '').strip()}\n\nSITUATION\n{data['situation'].strip()}")
    obj = data["objectives"]
    threats = "\n".join(f"- {t['name']} ({t.get('intel', 'confirmed').upper()}): {t.get('notes', '')}" for t in data.get("threats", []))
    m.set_description_bluetask_text(
        "OBJECTIVES\n" + "\n".join(f"{k.upper()}: {v}" for k, v in obj.items())
        + f"\n\nROE\n{data.get('roe', '').strip()}\n\nTHREATS\n{threats}")

    # pydcs picks tail numbers by popping from a set, which varies per process; number them in order instead
    tail = 100
    for g in groups.values():
        for u in g.units:
            if hasattr(u, "onboard_num") and hasattr(g, "frequency"):
                tail += 1
                u.onboard_num = f"{tail:03}"

    player_type = _type(dcs.planes, next(f for f in data["flights"] if f.get("player"))["aircraft"])
    for page in kneeboard_pages:
        m.add_aircraft_kneeboard(player_type, Path(page))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out_path))
    _pin_zip_timestamps(out_path)
    return m


def _set_callsign(group, callsign: str, country, ac, awacs: bool = False) -> None:
    """Give the group the DCS callsign the story uses ("Colt 1" -> Colt 1-1, Colt 1-2), when the country has it.

    Western callsigns index the country's list, followed by the aircraft type's own names (A-10: Hawg, Boar...).
    """
    word, _, num = callsign.partition(" ")
    names = country.callsign.get("AWACS" if awacs else "Air", []) + ([] if awacs else getattr(ac, "callnames", {}).get(country.name, []))
    lower = [n.lower() for n in names]
    if word.lower() not in lower:
        return  # e.g. red flights: Russian callsigns are numeric
    idx, num = lower.index(word.lower()), int(num) if num.isdigit() else 1
    for j, u in enumerate(group.units, 1):
        u.callsign_dict = {1: idx + 1, 2: num, 3: j, "name": f"{names[idx]}{num}{j}"}


def _set_presets(group, comms: list[dict]) -> None:
    """Put every comms-card frequency with a radio/channel onto the player aircraft's presets."""
    for u in group.units:
        if u.radio is None:
            u.set_radio_preset()
        for c in comms:
            if "radio" not in c or (c["radio"], c["channel"]) == (1, 1):
                continue  # DCS sets radio 1 channel 1 to the flight frequency itself
            mhz = float(str(c["freq"]).split()[0])
            if u.radio is None or c["radio"] not in u.radio:
                raise ValueError(f"{u.type} has no radio {c['radio']} for '{c['name']}'")
            u.set_radio_channel_preset(c["radio"], c["channel"], mhz)


def _when(when: dict, player_group, zones: dict, groups: dict, variant_flags: dict) -> list:
    """DCS conditions for a `when` block; every one must hold."""
    conds = []
    for kind, arg in when.items():
        if kind == "time_after":
            conds.append(condition.TimeAfter(arg))
        elif kind == "player_in_zone":
            # The human lead, not "any of the group": an AI wingman launching early mustn't advance the story
            conds.append(condition.UnitInZone(player_group.units[0].id, zones[arg].id))
        elif kind == "group_dead":
            conds.append(condition.GroupDead(groups[arg].id))
        elif kind == "flag":
            conds.append(condition.FlagIsTrue(arg))
        elif kind == "target_destroyed":
            conds.append(condition.FlagIsTrue(TARGET_FLAG))
        elif kind == "variant":
            conds.append(condition.FlagEquals(variant_flags[arg[0]], arg[1]))
        else:
            raise ValueError(f"unsupported trigger condition '{kind}'")
    return conds


def _actions(m: dcs.Mission, r, spec: dict, groups: dict) -> None:
    for g in spec.get("activate", []):
        r.add_action(action.ActivateGroup(groups[g].id))
    if "message" in spec:
        r.add_action(action.MessageToCoalition(action.Coalition.Blue, m.string(spec["message"]), spec.get("seconds", 10)))
    if "set_flag" in spec:
        r.add_action(action.SetFlag(spec["set_flag"]))


def _pin_zip_timestamps(path: Path) -> None:
    """Rewrite the .miz with fixed entry timestamps so unchanged missions don't show up in git diffs."""
    with zipfile.ZipFile(path) as z:
        entries = [(i.filename, z.read(i.filename)) for i in z.infolist()]
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, blob in entries:
            z.writestr(zipfile.ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0)), blob, compress_type=zipfile.ZIP_DEFLATED)


def _airport(terrain, name: str):
    ap = getattr(terrain, name.lower(), None) or terrain.airports.get(name.replace("_", "-"))
    if ap is None:
        for k, v in terrain.airports.items():
            if k.replace("-", "_").replace(" ", "_").lower() == name.lower():
                return v
        raise ValueError(f"unknown airport '{name}' on {terrain.name}")
    return ap
