import copy
import zipfile
from pathlib import Path

import pytest

import dcsmb  # noqa: F401  (silences pydcs import noise)
import dcs
from dcsmb import build_html, build_miz, schema

MISSION = Path(__file__).resolve().parent.parent / "missions" / "gudauta_bridge"


@pytest.fixture(scope="module")
def data():
    return schema.load(MISSION)


def test_validation_reports_every_problem(data):
    bad = copy.deepcopy(data)
    bad["target"]["lat"] = 123
    bad["storyboard"][2]["trigger"]["when"] = {"player_in_zone": "NOWHERE"}
    bad["storyboard"][3]["trigger"]["activate"] = ["Ghost Flight"]
    with pytest.raises(schema.MissionError) as e:
        schema.validate(bad)
    msg = str(e.value)
    assert "target: 'lat'" in msg
    assert "unknown waypoint 'NOWHERE'" in msg
    assert "unknown group 'Ghost Flight'" in msg


def test_miz_round_trip(data, tmp_path):
    page = tmp_path / "01_test.png"
    page.write_bytes(b"\x89PNG\r\n\x1a\n")
    miz = tmp_path / "m.miz"
    build_miz.build(data, miz, [page])

    with zipfile.ZipFile(miz) as z:
        names = z.namelist()
    assert "mission" in names
    assert any(n.startswith("KNEEBOARD/FA-18C_hornet/IMAGES/") for n in names)

    m = dcs.Mission()
    m.load_file(str(miz))
    groups = {g.name for c in m.coalition.values() for country in c.countries.values()
              for g in country.plane_group + country.vehicle_group}
    assert {"Enfield 1", "SA-6 Battery", "Bridge target", "OVERLORD", "Colt", "Red Alert"} <= groups

    # 2 target-destroyed helpers + one rule per storyboard trigger
    n_story = sum(1 for p in data["storyboard"] if p.get("trigger"))
    assert len(m.triggerrules.triggers) == 2 + n_story
    assert "TARGET BRIDGE" in {z.name for z in m.triggers.zones()}

    enfield = next(g for g in m.country("USA").plane_group if g.name == "Enfield 1")
    assert [p.name for p in enfield.points[1:-1]] == [w["name"] for w in data["flights"][0]["waypoints"]]
    tgt = enfield.points[1:-1][-3].position.latlng()
    assert tgt.lat == pytest.approx(data["target"]["lat"], abs=1e-6)


def test_html_contains_story_and_map(data, tmp_path):
    out = build_html.build(data, tmp_path / "b.html")
    html = out.read_text()
    assert data["narrative"]["operation"] in html
    for ph in data["storyboard"]:
        assert ph["phase"].replace("&", "&amp;") in html
    assert '"route"' in html and "leaflet" in html
