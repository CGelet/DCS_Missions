"""mission.yaml -> pydcs Mission -> .miz"""
from __future__ import annotations

import random
import zipfile
from datetime import date, datetime
from pathlib import Path

import dcs
from dcs import action, condition, task, triggers, weather
from dcs.goals import Goal
from dcs.mission import StartType
from dcs.point import MovingPoint, PointAction, PointProperties
from dcs.terrain import Caucasus

from .geo import FT, KTS, NM, point
from .schema import phase_triggers

TARGET_FLAG = 99          # set by any target-destroyed helper rule
SUCCESS_FLAG = 10         # every mission's success trigger sets it; the mission goal scores on it
CHANCE_FLAG_BASE = 200    # one flag per `chance` trigger, rolled at mission start
VARIANT_FLAG_BASE = 300   # default flag for variants without an explicit one
TIMING_FLAG_BASE = 400    # timed checkpoints: start-of-leg and window flags
DEFAULT_ZONE_KM = 10
START_TYPES = {"cold": StartType.Cold, "warm": StartType.Warm, "runway": StartType.Runway}
MAINTASKS = {"bomb": task.GroundAttack, "sead": task.SEAD, "cas": task.CAS, "cap": task.CAP, "intercept": task.Intercept,
             "antiship": task.AntishipStrike}
AI_FLIGHT_TASKS = {"antiship": task.AntishipStrike, "sweep": task.FighterSweep, "cap": task.CAP, "strike": task.GroundAttack,
                   "transport": task.Transport, "sead": task.SEAD}


def _type(module, name: str):
    try:
        return getattr(module, name)
    except AttributeError:
        raise ValueError(f"unknown unit type '{name}' in {module.__name__}") from None


def _aircraft(name: str):
    """Planes and helicopters live in different pydcs modules."""
    t = getattr(dcs.planes, name, None) or getattr(dcs.helicopters, name, None)
    if t is None:
        raise ValueError(f"unknown aircraft type '{name}' (not in dcs.planes or dcs.helicopters)")
    return t


def _weapon(ac, pylon: int, name: str):
    station = getattr(ac, f"Pylon{pylon}", None)
    if station is None:
        raise ValueError(f"{ac.__name__} has no pylon {pylon}")
    if not hasattr(station, name):
        close = sorted(a for a in dir(station) if not a.startswith("_") and name.split("_")[0].lower() in a.lower())
        raise ValueError(f"{ac.__name__} pylon {pylon} has no weapon '{name}'. Similar names: {close[:8] or 'none'}")
    return getattr(station, name)


def _vehicle(name: str):
    for cat in ("AirDefence", "Armor", "Unarmed", "Infantry", "Artillery", "MissilesSS", "Fortification"):
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
    if w.get("cloud_preset"):  # real DCS clouds; without it the `clouds` line is briefing text only
        from dcs.cloud_presets import Clouds
        m.weather.clouds_preset = Clouds[w["cloud_preset"]].value
        m.weather.clouds_base = int(w["cloud_base_ft"] * FT)
    if w.get("fog_visibility_m"):
        m.weather.enable_fog = True
        m.weather.fog_visibility = w["fog_visibility_m"]
        m.weather.fog_thickness = w.get("fog_thickness_m", 300)

    groups: dict[str, object] = {}
    zones: dict[str, object] = {}

    # --- named zones (for triggers on things other than the player's waypoints) --
    for z in data.get("zones", []):
        zones[z["name"]] = m.triggers.add_triggerzone(point(terrain, z), radius=z["radius_km"] * 1000, name=z["name"])

    # --- ships (built first: flights can launch from them) --------------
    ships: dict[str, object] = {}
    for sh in data.get("ships", []):
        country = red if sh.get("coalition") == "red" else blue
        types = [_type(dcs.ships, t) for t in sh["type"]]
        pos = point(terrain, sh)
        sg = m.ship_group(country, sh["name"], types[0], pos, heading=sh.get("heading", 0))
        for i, t in enumerate(types[1:], 1):  # escorts in a loose line astern
            u = m.ship(f"{sh['name']} {i + 1}", t)
            u.position = pos.point_from_heading((sh.get("heading", 0) + 180) % 360, 1500 * i)
            u.heading = sh.get("heading", 0)
            sg.add_unit(u)
        for p in sh.get("route", []):
            sg.add_waypoint(point(terrain, p), sh.get("speed_kts", 20) * KTS)
        lead = sg.units[0]
        if "tacan" in sh:
            ch, mode = int(sh["tacan"]["channel"][:-1]), sh["tacan"]["channel"][-1]
            sg.points[0].tasks.append(task.ActivateBeaconCommand(ch, mode, sh["tacan"].get("callsign", "SHP"),
                                                                 unit_id=lead.id, aa=False))
        if "icls" in sh:
            sg.points[0].tasks.append(task.ActivateICLSCommand(sh["icls"], unit_id=lead.id))
        if "freq_mhz" in sh:
            sg.set_frequency(int(sh["freq_mhz"] * 1_000_000))
        sg.late_activation = bool(sh.get("late_activation"))
        ships[sh["name"]] = groups[sh["name"]] = sg

    # --- flights ---------------------------------------------------------
    for f in data["flights"]:
        ac = _aircraft(f["aircraft"])
        actions = {wp.get("action") for wp in f["waypoints"]}
        maintask = next((t for a, t in MAINTASKS.items() if a in actions), task.GroundAttack)
        start_type = START_TYPES[f.get("start", "cold")]
        if f["base"] in ships:
            fg = m.flight_group_from_unit(blue, f["callsign"], ac, ships[f["base"]], maintask=maintask,
                                          start_type=start_type, group_size=f.get("count", 1))
        else:
            fg = m.flight_group_from_airport(blue, f["callsign"], ac, _airport(terrain, f["base"]), maintask=maintask,
                                             start_type=start_type, group_size=f.get("count", 1))
        groups[f["callsign"]] = fg
        if maintask is task.AntishipStrike:
            # pydcs's default en-route task engages *any* ship; merchants must be safe from the AI wingman
            fg.points[0].tasks = [t for t in fg.points[0].tasks if not isinstance(t, task.AntishipStrikeTaskAction)]
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
            if wp.get("agl"):
                mp.alt_type = "RADIO"  # height above ground: terrain-following legs
            # Tasks steer the AI wingman; the player flies their own plan.
            if wp.get("action") == "bomb":
                tgt = point(terrain, data["target"])
                mp.tasks.append(task.Bombing(tgt, weapon_type=task.WeaponType.Guided, group_attack=True))
            elif wp.get("action") == "sead":
                mp.tasks.append(task.EngageTargets(max_distance=80_000, targets=[task.Targets.All.GroundUnits.AirDefence]))
            elif wp.get("action") == "cas":
                mp.tasks.append(task.EngageTargets(max_distance=15_000, targets=[task.Targets.All.GroundUnits]))
            elif wp.get("action") == "antiship":
                # Armed ships only, so the AI wingman never Harpoons a merchant
                mp.tasks.append(task.EngageTargets(max_distance=130_000, targets=[task.Targets.All.Naval.Ships.ArmedShips]))
            zones[wp["name"]] = m.triggers.add_triggerzone(
                pt, radius=wp.get("zone_km", DEFAULT_ZONE_KM) * 1000, name=f"ZONE {wp['name']}")
        if f.get("land") in ships:
            _land_on_ship(fg, ships[f["land"]])
        elif "land" in f:
            fg.land_at(_airport(terrain, f["land"]))

    player_group = next(groups[f["callsign"]] for f in data["flights"] if f.get("player"))

    # --- ground units ----------------------------------------------------
    for u in data.get("units", []):
        country = red if u.get("coalition", "red") == "red" else blue
        vg = m.vehicle_group_platoon(country, u["name"], [_vehicle(t) for t in u["type"]],
                                     point(terrain, u), heading=u.get("heading", 0))
        vg.late_activation = bool(u.get("late_activation"))
        if u.get("hold_fire"):  # range targets and other units that mustn't shoot back
            vg.points[0].tasks.append(task.OptROE(task.OptROE.Values.WeaponHold))
        for p in u.get("route", []):
            vg.add_waypoint(point(terrain, p), PointAction.OnRoad if u.get("on_road", True) else PointAction.OffRoad,
                            u.get("speed_kmh", 25))
        groups[u["name"]] = vg

    # --- support flights -------------------------------------------------
    for s in data.get("support", []):
        country = red if s.get("coalition") == "red" else blue
        ac = _aircraft(s["aircraft"])
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
        elif s["kind"] == "tanker":
            g = m.refuel_flight(country, s["callsign"], ac, None, point(terrain, s),
                                race_distance=s.get("leg_nm", 30) * NM, heading=s.get("heading", 0),
                                altitude=s.get("alt_ft", 20000) * FT, speed=s.get("kts", 280) * KTS,
                                frequency=s.get("freq_mhz", 251))
            # pydcs's beacon has no unit id or callsign; replace it with one DCS can tie to the tanker
            g.points[0].tasks = [t for t in g.points[0].tasks if not isinstance(t, task.ActivateBeaconCommand)]
            if "tacan" in s:
                ch, mode = int(s["tacan"]["channel"][:-1]), s["tacan"]["channel"][-1]
                g.points[0].tasks.append(task.ActivateBeaconCommand(ch, mode, s["tacan"].get("callsign", "TKR"),
                                                                    unit_id=g.units[0].id, aa=True))
        elif s["kind"] == "flight":
            # A generic AI flight that spawns in the air and flies a route (raids, sweeps)
            sp = s["spawn"]
            g = m.flight_group_inflight(country, s["callsign"], ac, point(terrain, sp), sp.get("alt_ft", 20000) * FT,
                                        sp.get("kts", 450) * KTS, maintask=AI_FLIGHT_TASKS[s["task"]],
                                        group_size=s.get("count", 2))
            for i, p in enumerate(s.get("route", [])):
                mp = g.add_waypoint(point(terrain, p), p.get("alt_ft", sp.get("alt_ft", 20000)) * FT,
                                    p.get("kts", sp.get("kts", 450)) * KTS)
                if p.get("agl"):
                    mp.alt_type = "RADIO"
                if i == 0 and s["task"] == "antiship" and s.get("attack") in ships:
                    mp.tasks.append(task.AttackGroup(ships[s["attack"]].id))
                elif i == 0 and s["task"] == "sead":
                    mp.tasks.append(task.EngageTargets(max_distance=60_000, targets=[task.Targets.All.GroundUnits.AirDefence]))
                elif i == 0 and s["task"] in ("sweep", "cap"):
                    mp.tasks.append(task.EngageTargets(max_distance=80_000, targets=[task.Targets.All.Air]))
                if p.get("land_s"):  # helicopters: set down here for this many seconds, then carry on
                    mp.tasks.append(task.Land(mp.position, p["land_s"]))
        elif s["kind"] == "intercept":
            g = m.flight_group_from_airport(country, s["callsign"], ac, _airport(terrain, s["base"]),
                                            maintask=task.Intercept, start_type=StartType.Runway,
                                            group_size=s.get("count", 2))
            mp = g.add_waypoint(point(terrain, data["target"]), 6000, 900)
            mp.tasks.append(task.EngageTargets(max_distance=60_000, targets=[task.Targets.All.Air]))
        else:
            raise ValueError(f"support kind '{s['kind']}' not supported")
        g.late_activation = bool(s.get("late_activation"))
        _set_callsign(g, s["callsign"], country, ac, kind=s["kind"])
        groups[s["callsign"]] = g

    # --- random variants (rolled once at mission start) ---------------
    variant_of: dict[str, list[tuple[int, int]]] = {}  # group -> every (flag, option number) that activates it
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
                variant_of.setdefault(g, []).append((flag, n_opt))

    # --- target-destroyed helpers ---------------------------------------
    tgt = data["target"]
    helpers = []
    if tgt.get("zone_m"):
        tz = m.triggers.add_triggerzone(point(terrain, tgt), radius=tgt["zone_m"], name="TARGET ZONE")
        helpers.append([condition.MapObjectIsDead(tz.id)])
    kill = tgt.get("kill_pct", 100)
    for g in tgt.get("groups", []):
        gid = groups[g].id
        dead = lambda: condition.GroupDead(gid) if kill == 100 else condition.GroupLifeLess(gid, 100 - kill)
        # Only a variant that actually spawned the group counts: one helper per option that does
        for flag_opt in variant_of.get(g, [None]):
            helpers.append([dead()] + ([condition.FlagEquals(*flag_opt)] if flag_opt else []))
    for conds in helpers:
        r = triggers.TriggerOnce(comment="target destroyed helper")
        for c in conds:
            r.add_condition(c)
        r.add_action(action.SetFlag(TARGET_FLAG))
        m.triggerrules.triggers.append(r)

    # --- timed checkpoints (training) -------------------------------------
    # Arriving at a waypoint with `timing` says early / on time / late against its planned time from an
    # earlier waypoint. DCS has no "time less than", so window-open and window-closed flags do the comparison.
    player_f = next(f for f in data["flights"] if f.get("player"))
    timed = [wp for wp in player_f["waypoints"] if wp.get("timing")]
    start_flags: dict[str, int] = {}
    tflag = TIMING_FLAG_BASE
    for origin in dict.fromkeys(wp["timing"]["from"] for wp in timed):
        tflag += 1
        start_flags[origin] = tflag
        r = triggers.TriggerOnce(comment=f"timing: clock starts at {origin}")
        r.add_condition(condition.UnitInZone(player_group.units[0].id, zones[origin].id))
        r.add_action(action.SetFlag(tflag))
        m.triggerrules.triggers.append(r)
    for wp in timed:
        tm, name = wp["timing"], wp["name"]
        win = tm.get("window_s", 30)
        start, w_open, w_close, judged = start_flags[tm["from"]], tflag + 1, tflag + 2, tflag + 3
        tflag += 3
        for flag, secs in ((w_open, tm["seconds"] - win), (w_close, tm["seconds"] + win)):
            r = triggers.TriggerOnce(comment=f"timing: {name} window flag")
            r.add_condition(condition.TimeSinceFlag(start, max(secs, 1)))
            r.add_action(action.SetFlag(flag))
            m.triggerrules.triggers.append(r)
        in_zone = lambda: condition.UnitInZone(player_group.units[0].id, zones[name].id)
        for verdict, conds, extra in (("EARLY", [condition.FlagIsTrue(start), condition.FlagIsFalse(w_open)], None),
                                      ("ON TIME", [condition.FlagIsTrue(w_open), condition.FlagIsFalse(w_close)], tm["flag"]),
                                      ("LATE", [condition.FlagIsTrue(w_close)], None)):
            r = triggers.TriggerOnce(comment=f"timing: {name} {verdict.lower()}")
            for c in [in_zone(), *conds, condition.FlagIsFalse(judged)]:  # one verdict per checkpoint
                r.add_condition(c)
            r.add_action(action.SetFlag(judged))
            r.add_action(action.MessageToCoalition(action.Coalition.Blue, m.string(
                f"TIMING: {name} {verdict} (plan {tm['seconds'] // 60}:{tm['seconds'] % 60:02d} from {tm['from']}, ±{win} s)"), 10))
            if extra:
                r.add_action(action.SetFlag(extra))
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

    # --- mission goal: DCS scores 100 on success, 0 otherwise (campaigns advance on > 50) ---
    goal = Goal("Mission success", score=100)
    goal.rules.append(condition.FlagIsTrue(SUCCESS_FLAG))
    m.goals.add_blue(goal)

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

    player_type = _aircraft(next(f for f in data["flights"] if f.get("player"))["aircraft"])
    for page in kneeboard_pages:
        m.add_aircraft_kneeboard(player_type, Path(page))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out_path))
    _pin_zip_timestamps(out_path)
    return m


def _set_callsign(group, callsign: str, country, ac, kind: str = "") -> None:
    """Give the group the DCS callsign the story uses ("Colt 1" -> Colt 1-1, Colt 1-2), when the country has it.

    Western callsigns index the country's list, followed by the aircraft type's own names (A-10: Hawg, Boar...).
    """
    word, _, num = callsign.partition(" ")
    if kind in ("awacs", "tanker"):
        names = country.callsign.get("AWACS" if kind == "awacs" else "Tankers", [])
    else:
        names = country.callsign.get("Air", []) + getattr(ac, "callnames", {}).get(country.name, [])
    lower = [n.lower() for n in names]
    if word.lower() not in lower:
        return  # e.g. red flights: Russian callsigns are numeric
    idx, num = lower.index(word.lower()), int(num) if num.isdigit() else 1
    for j, u in enumerate(group.units, 1):
        u.callsign_dict = {1: idx + 1, 2: num, 3: j, "name": f"{names[idx]}{num}{j}"}


def _land_on_ship(fg, sg) -> None:
    """Final waypoint: recover aboard the ship (DCS follows the ship, so the position is only nominal)."""
    pos = sg.points[-1].position if sg.points else sg.units[0].position
    mp = MovingPoint(pos)
    mp.type, mp.action = "Land", PointAction.Landing
    mp.helipad_id = mp.link_unit = sg.units[0].id
    mp.alt, mp.speed = 0, 250 * KTS / 3.6
    mp.properties = PointProperties()
    fg.add_point(mp)


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
        elif kind == "group_life_below":
            conds.append(condition.GroupLifeLess(groups[arg[0]].id, arg[1]))
        elif kind == "group_in_zone":
            conds.append(condition.PartOfGroupInZone(groups[arg[0]].id, zones[arg[1]].id))
        elif kind == "flag":  # one flag or a list, all set
            conds += [condition.FlagIsTrue(f) for f in (arg if isinstance(arg, list) else [arg])]
        elif kind == "flag_false":
            conds += [condition.FlagIsFalse(f) for f in (arg if isinstance(arg, list) else [arg])]
        elif kind == "target_destroyed":
            conds.append(condition.FlagIsTrue(TARGET_FLAG))
        elif kind == "time_since_flag":
            conds.append(condition.TimeSinceFlag(arg[0], arg[1]))
        elif kind == "player_below_ft":
            conds.append(condition.UnitAltitudeLower(player_group.units[0].id, arg * FT))
        elif kind == "scenery_dead":  # a map object (bridge, building) inside the zone is destroyed
            conds.append(condition.MapObjectIsDead(zones[arg].id))
        elif kind == "player_above_ft":
            conds.append(condition.UnitAltitudeHigher(player_group.units[0].id, arg * FT))
        elif kind == "player_slower_kts":  # with player_below_ft over the sea: on the deck
            conds.append(condition.UnitSpeedLower(player_group.units[0].id, arg * KTS / 3.6))
        elif kind == "player_below_agl_ft":
            conds.append(condition.UnitAltitudeLowerAGL(player_group.units[0].id, arg * FT))
        elif kind == "variant":
            conds.append(condition.FlagEquals(variant_flags[arg[0]], arg[1]))
        else:
            raise ValueError(f"unsupported trigger condition '{kind}'")
    return conds


def _actions(m: dcs.Mission, r, spec: dict, groups: dict) -> None:
    for g in spec.get("activate", []):
        r.add_action(action.ActivateGroup(groups[g].id))
    for g in spec.get("deactivate", []):
        r.add_action(action.DeactivateGroup(groups[g].id))
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
