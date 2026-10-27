import copy
import re
import zipfile
from pathlib import Path

import pytest

import dcsmb  # noqa: F401  (silences pydcs import noise)
import dcs
from dcsmb import build_director, build_html, build_miz, build_slides, schema
from dcsmb.schema import phase_triggers

MISSIONS = sorted(p.parent for p in (Path(__file__).resolve().parent.parent / "missions").glob("*/mission.yaml"))


@pytest.fixture(scope="module", params=MISSIONS, ids=lambda p: p.name)
def data(request):
    return schema.load(request.param)


@pytest.fixture(scope="module")
def bridge():
    return schema.load(next(p for p in MISSIONS if p.name == "gudauta_bridge"))


def test_validation_reports_every_problem(bridge):
    bad = copy.deepcopy(bridge)
    bad["target"]["lat"] = 123
    bad["storyboard"][2]["trigger"]["when"] = {"player_in_zone": "NOWHERE"}
    bad["storyboard"][3]["trigger"]["activate"] = ["Ghost Flight"]
    bad["storyboard"][0]["trigger"]["chance"] = 100
    bad["threats"][0]["intel"] = "rumour"
    del bad["storyboard"][1]["brief"]
    with pytest.raises(schema.MissionError) as e:
        schema.validate(bad)
    msg = str(e.value)
    assert "target: 'lat'" in msg
    assert "unknown waypoint 'NOWHERE'" in msg
    assert "unknown group 'Ghost Flight'" in msg
    assert "'chance' is a percentage" in msg
    assert "'intel' must be one of" in msg
    assert "needs 'phase' and 'brief'" in msg


def test_activating_an_already_active_group_is_an_error(bridge):
    bad = copy.deepcopy(bridge)
    bad["storyboard"][2]["trigger"]["activate"] = ["Bridge AAA"]
    with pytest.raises(schema.MissionError, match="needs 'late_activation: true'"):
        schema.validate(bad)


def _expected_rules(data) -> int:
    trigs = [t for ph in data["storyboard"] for t in phase_triggers(ph)]
    chance_rolls = sum(1 for t in trigs if "chance" in t)
    variants = sum(1 + len(v["options"]) for v in data.get("variants", []))
    tgt = data["target"]
    helpers = (1 if tgt.get("zone_m") else 0) + len(tgt.get("groups", []))
    return len(trigs) + chance_rolls + variants + helpers


def test_miz_round_trip(data, tmp_path):
    page = tmp_path / "01_test.png"
    page.write_bytes(b"\x89PNG\r\n\x1a\n")
    miz = tmp_path / "m.miz"
    build_miz.build(data, miz, [page])

    with zipfile.ZipFile(miz) as z:
        names = z.namelist()
    player = next(f for f in data["flights"] if f.get("player"))
    ac = getattr(dcs.planes, player["aircraft"])
    assert f"KNEEBOARD/{ac.id}/IMAGES/01_test.png" in names

    m = dcs.Mission()
    m.load_file(str(miz))
    groups = {g.name: g for c in m.coalition.values() for country in c.countries.values()
              for g in country.plane_group + country.vehicle_group}
    expected = {player["callsign"]} | {u["name"] for u in data.get("units", [])} | {s["callsign"] for s in data.get("support", [])}
    assert expected <= set(groups)
    for u in data.get("units", []):
        assert groups[u["name"]].late_activation == bool(u.get("late_activation"))
        assert len(groups[u["name"]].points) == 1 + len(u.get("route", []))

    assert len(m.triggerrules.triggers) == _expected_rules(data)

    lead = groups[player["callsign"]]
    assert [p.name for p in lead.points[1:-1]] == [w["name"] for w in player["waypoints"]]
    wp0 = lead.points[1].position.latlng()
    assert wp0.lat == pytest.approx(player["waypoints"][0]["lat"], abs=1e-6)


def _spoilers(data) -> list[str]:
    """Strings that must never appear in pilot-facing output."""
    out = []
    for ph in data["storyboard"]:
        if ph.get("script"):
            out.append(ph["script"].strip().split("\n")[0])
        out += [t["message"] for t in phase_triggers(ph) if t.get("message")]
    for v in data.get("variants", []):
        out += [o["label"] for o in v["options"]] + [o["message"] for o in v["options"] if o.get("message")]
    out += [u["name"] for u in data.get("units", []) if u.get("late_activation")]
    out += [s["callsign"] for s in data.get("support", []) if s.get("coalition") == "red"]
    out += [o.strip().split("\n")[0] for o in data["narrative"].get("outcomes", {}).values()]
    return [s for s in out if s]


def _text(html: str) -> str:
    import html as h
    return h.unescape(re.sub(r"\s+", " ", html))


def test_pilot_outputs_have_no_spoilers(data, tmp_path):
    pilot = _text(build_html.build(data, tmp_path / "b.html").read_text())
    pilot += _text(build_slides.build(data, tmp_path / "s.html").read_text())
    leaks = [s for s in _spoilers(data) if re.sub(r"\s+", " ", s) in pilot]
    assert not leaks, f"pilot-facing pages leak: {leaks}"


def test_director_has_everything(data, tmp_path):
    director = _text(build_director.build(data, tmp_path / "d.html").read_text())
    missing = [s for s in _spoilers(data) if re.sub(r"\s+", " ", s) not in director]
    assert not missing, f"director view is missing: {missing}"


def test_slides_cover_story_and_every_phase(data, tmp_path):
    deck = build_slides.slides(data)
    kinds = [s["kind"] for s in deck]
    assert kinds[0] == "title" and "outcome" not in kinds
    phases = [s for s in deck if s["kind"] == "phase"]
    assert [s["title"] for s in phases] == [p["phase"] for p in data["storyboard"]]
    assert all(s["svg"] for s, p in zip(phases, data["storyboard"]) if p.get("waypoints"))
    html = build_slides.build(data, tmp_path / "s.html").read_text()
    assert html.count('<section class="slide') == len(deck)
