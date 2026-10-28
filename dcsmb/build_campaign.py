"""campaign.yaml -> hangar/campaigns/<id>/: campaign page, DCS .cmp campaign file, and the chapters' .miz files.

DCS resolves a campaign's missions relative to its .cmp, so a campaign mission's .miz is built straight
into the campaign folder (not hangar/<mission>/) and the whole folder installs as one.
"""
from __future__ import annotations

from pathlib import Path

from .build_hangar import card
from .build_html import env
from .build_miz import _aircraft


def miz_path(data: dict, hangar: Path) -> Path:
    c = data.get("campaign")
    if c:
        return hangar / "campaigns" / c["id"] / f"{c['chapter']:02}_{data['meta']['id']}.miz"
    return hangar / data["meta"]["id"] / f"{data['meta']['id']}.miz"


def _lua(v, indent: int = 0) -> str:
    pad = "    " * indent
    if isinstance(v, dict):
        items = [f'{pad}    [{k if isinstance(k, int) else _lua(k)}] = {_lua(x, indent + 1)},' for k, x in v.items()]
        return "\n".join(["{", *items, pad + "}"])
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
    return f'"{s}"'


def cmp_text(c: dict, chapters: list[dict], hangar: Path) -> str:
    """Linear campaign: one stage per chapter. A chapter passes when its mission goal scores over 50
    (build_miz gives 100 for the success flag), otherwise DCS replays the stage."""
    aircraft = {}
    for d in chapters:
        ac = _aircraft(next(f for f in d["flights"] if f.get("player"))["aircraft"]).id
        aircraft[ac] = ac
    premise = " ".join(c["premise"].split())  # DCS shows it as one paragraph
    desc = f"{c.get('subtitle', '')}\n\n{premise}".strip()
    camp = {
        "name": c["title"], "name_EN": c["title"],
        "description": desc, "description_EN": desc,
        "necessaryUnits": aircraft,
        "version": 1,
        "startStage": 1,
        "stages": {i: {"name": f"Chapter {i}: {d['meta'].get('subtitle') or d['meta']['title']}",
                       "missions": {1: {"file": miz_path(d, hangar).name, "description": "", "interval": {1: 0, 2: 100}}}}
                   for i, d in enumerate(chapters, 1)},
    }
    return f"campaign = \n{_lua(camp)} -- end of campaign\n"


def build(c: dict, missions, hangar: Path) -> list[Path]:
    by_id = {m["meta"]["id"]: m for m in missions}
    chapters = [by_id[ch["mission"]] for ch in c["chapters"]]
    out_dir = hangar / "campaigns" / c["id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    cards = []
    for i, (ch, d) in enumerate(zip(c["chapters"], chapters), 1):
        cards.append({**card(d, hangar), "chapter": i, "previously": d["campaign"]["previously"], "miz_name": miz_path(d, hangar).name})
    keep = {miz_path(d, hangar).name for d in chapters}
    for old in out_dir.glob("*.miz"):  # chapters that were renumbered or dropped
        if old.name not in keep:
            old.unlink()
    cmp = out_dir / f"{c['id']}.cmp"
    cmp.write_text(cmp_text(c, chapters, hangar))
    written = [cmp]
    for name in ("index.html", "README.md"):
        path = out_dir / name
        path.write_text(env().get_template(f"campaign.{name.split('.')[1]}.j2").render(c=c, chapters=cards))
        written.append(path)
    return written


def summary(c: dict, missions) -> dict:
    """Hangar card for a campaign."""
    by_id = {m["meta"]["id"]: m for m in missions}
    chapters = [by_id[ch["mission"]] for ch in c["chapters"]]
    dates = [str(d["meta"]["date"]) for d in chapters]
    return {"id": c["id"], "title": c["title"], "subtitle": c.get("subtitle", ""), "category": c.get("category", "operational"),
            "premise": c["premise"].strip(), "count": len(chapters), "first": dates[0], "last": dates[-1],
            "setting": c.get("setting", "")}
