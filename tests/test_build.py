import copy
import json
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
    assert "unknown waypoint or zone 'NOWHERE'" in msg
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
    # one helper per target group, or one per variant option that spawns it
    spawns = lambda g: sum(g in o.get("activate", []) for v in data.get("variants", []) for o in v["options"]) or 1
    helpers = (1 if tgt.get("zone_m") else 0) + sum(spawns(g) for g in tgt.get("groups", []))
    # timed checkpoints: one clock-start rule per origin, then 2 window flags + 3 verdicts per checkpoint
    player = next(f for f in data["flights"] if f.get("player"))
    timed = [w for w in player["waypoints"] if w.get("timing")]
    timing = len({w["timing"]["from"] for w in timed}) + 5 * len(timed)
    return len(trigs) + chance_rolls + variants + helpers + timing


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
              for g in country.plane_group + country.helicopter_group + country.vehicle_group + country.ship_group}
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
    if data["meta"].get("category") != "training":  # training briefs the adversaries and range targets openly
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


# --- campaigns ------------------------------------------------------------------
from dcsmb import build_campaign  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CAMPAIGN_DIRS = sorted(p.parent for p in (ROOT / "campaigns").glob("*/campaign.yaml"))


@pytest.fixture(scope="module")
def everything():
    missions = [schema.load(p) for p in MISSIONS]
    return missions, schema.load_campaigns(ROOT / "campaigns", missions)


def _lua_table(text: str):
    """Just enough Lua to read back our own .cmp: keyed tables, strings, numbers."""
    import ast
    body = text.split("=", 1)[1].rsplit("-- end of campaign", 1)[0]
    body = re.sub(r'\[("(?:[^"\\]|\\.)*"|\d+)\]\s*=', r"\1:", body)
    return ast.literal_eval(body.replace("true", "True").replace("false", "False"))


def test_campaign_validation(tmp_path, bridge):
    camp = tmp_path / "c" / "x"
    camp.mkdir(parents=True)
    (camp / "campaign.yaml").write_text(
        "id: x\ntitle: X\npremise: p\ncategory: training\nchapters:\n  - mission: gudauta_bridge\n    previously: recap\n  - mission: nowhere\n")
    with pytest.raises(schema.MissionError) as e:
        schema.load_campaigns(tmp_path / "c", [copy.deepcopy(bridge)])
    msg = str(e.value)
    assert "unknown mission 'nowhere'" in msg
    assert "is operational, campaign is training" in msg
    assert "chapter 1 can't have 'previously'" in msg


def test_mission_needs_success_flag(bridge):
    bad = copy.deepcopy(bridge)
    for ph in bad["storyboard"]:
        for t in phase_triggers(ph):
            if t.get("set_flag") == 10:
                del t["set_flag"]
    with pytest.raises(schema.MissionError, match="sets flag 10"):
        schema.validate(bad)


@pytest.mark.parametrize("cdir", CAMPAIGN_DIRS, ids=lambda p: p.name)
def test_campaign_builds(cdir, everything, tmp_path):
    missions, campaigns = everything
    c = next(c for c in campaigns if c["id"] == cdir.name)
    by_id = {m["meta"]["id"]: m for m in missions}
    chapters = [by_id[ch["mission"]] for ch in c["chapters"]]
    for i, d in enumerate(chapters, 1):
        assert d["campaign"]["chapter"] == i and d["campaign"]["of"] == len(chapters)
        build_miz.build(d, build_campaign.miz_path(d, tmp_path))
    paths = build_campaign.build(c, missions, tmp_path)
    cmp = _lua_table(paths[0].read_text())
    assert cmp["startStage"] == 1 and len(cmp["stages"]) == len(chapters)
    for i, d in enumerate(chapters, 1):
        f = paths[0].parent / cmp["stages"][i]["missions"][1]["file"]
        assert f.exists()
        m = dcs.Mission()
        m.load_file(str(f))
        assert [g.score for g in m.goals.goals["blue"]] == [100]
    # The campaign page is pilot-facing: nothing from any chapter's director side
    page = _text((paths[0].parent / "index.html").read_text())
    for d in chapters:
        leaks = [s for s in _spoilers(d) if re.sub(r"\s+", " ", s) in page]
        assert not leaks, f"campaign page leaks {d['meta']['id']}: {leaks}"
        pilot = _text(build_html.build(d, tmp_path / "b.html").read_text()) + _text(build_slides.build(d, tmp_path / "s.html").read_text())
        assert f"Chapter {d['campaign']['chapter']} of" in pilot
        if d["campaign"]["previously"]:
            assert re.sub(r"\s+", " ", d["campaign"]["previously"]) in pilot


EVIL = '</script><img src=x onerror="alert(1)"><!--'


def test_yaml_text_cannot_inject_html(bridge, tmp_path):
    """Names and notes from mission.yaml are text on every page, never markup or script."""
    bad = copy.deepcopy(bridge)
    bad["threats"][0]["name"] = bad["threats"][0]["notes"] = EVIL
    bad["target"]["name"] = bad["target"]["description"] = EVIL
    bad["situation"] = EVIL
    for build, name in ((build_html.build, "b.html"), (build_director.build, "d.html"), (build_slides.build, "s.html")):
        page = build(bad, tmp_path / name).read_text()
        assert "<img src=x" not in page and "</script><img" not in page
        m = re.search(r"const D = (.*);\n", page)
        if m:  # the map data still parses back to the original text
            assert json.loads(m.group(1))["target"]["name"] == EVIL
            assert "const esc = " in page


def test_mission_id_must_be_a_plain_folder_name(bridge):
    bad = copy.deepcopy(bridge)
    bad["meta"]["id"] = "../../outside"
    with pytest.raises(schema.MissionError, match="meta.id"):
        schema.validate(bad)


def test_pages_lock_down_scripts():
    for t in ("briefing", "director", "slides", "home", "missions", "campaign"):
        src = (Path(__file__).resolve().parent.parent / "templates" / f"{t}.html.j2").read_text()
        assert '{% include "_security.html" %}' in src, t
        for tag in re.findall(r"<(?:script|link)[^>]*cdnjs[^>]*>", src):
            assert "integrity=" in tag, (t, tag)


def test_launcher_opens_the_hangar():
    root = Path(__file__).resolve().parent.parent
    src = (root / "Mission Hangar.html").read_text()
    targets = set(re.findall(r'url=([^"]+)"', src)) | set(re.findall(r'href="([^"]+)"', src))
    assert targets == {"hangar/index.html"} and (root / "hangar" / "index.html").exists()
