"""Hangar index: hangar/index.html (open locally) and hangar/README.md (renders on GitHub)."""
from __future__ import annotations

from pathlib import Path

from .build_html import env

AIRCRAFT_NAMES = {"FA_18C_hornet": "F/A-18C Hornet", "F_16C_50": "F-16C Viper", "A_10C_2": "A-10C II",
                  "F_14B": "F-14B Tomcat", "AV8BNA": "AV-8B Harrier",
                  "MiG_29S": "MiG-29S", "Su_27": "Su-27", "Tu_22M3": "Tu-22M3", "E_3A": "E-3A", "E_2C": "E-2C",
                  "KC135MPRS": "KC-135 (drogue)", "KC130": "KC-130", "S_3B_Tanker": "S-3B tanker",
                  "UH_60A": "UH-60A Black Hawk", "F_5E_3": "F-5E Tiger II"}


def features(data: dict) -> list[str]:
    """Filterable traits, derived from the mission so they can't go stale."""
    player = next(f for f in data["flights"] if f.get("player"))
    ships = {sh["name"] for sh in data.get("ships", [])}
    out = []
    if player["base"] in ships or player.get("land") in ships:
        out.append("Carrier")
    if any(s["kind"] == "tanker" and s.get("coalition", "blue") == "blue" for s in data.get("support", [])):
        out.append("Air refuelling")
    if any(wp.get("agl") or wp.get("alt_ft", 99999) <= 1000 for wp in player["waypoints"]):
        out.append("Low level")
    if player.get("land", player["base"]) != player["base"]:
        out.append("Different recovery field")
    if player.get("start") in ("runway", "warm"):
        out.append("Hot start")
    return out


def card(data: dict, hangar: Path) -> dict:
    from .build_campaign import miz_path
    meta, player = data["meta"], next(f for f in data["flights"] if f.get("player"))
    camp = data.get("campaign")
    teaser = data["narrative"]["backstory"].strip().split("\n\n")[0].replace("\n", " ")
    return {
        "id": meta["id"],
        "operation": data["narrative"].get("operation", meta["title"]),
        "category": meta.get("category", "operational"),
        "eyebrow": (f"Training · {data['training']['syllabus']}" if meta.get("category") == "training" and data.get("training", {}).get("syllabus")
                    else "Training event" if meta.get("category") == "training" else f"Operation {data['narrative'].get('operation', meta['title'])}"),
        "title": meta.get("subtitle") or meta["title"],
        "theater": meta["theater"].title(),
        "aircraft": f"{player.get('count', 1)}× {AIRCRAFT_NAMES.get(player['aircraft'], player['aircraft'])}",
        "aircraft_type": AIRCRAFT_NAMES.get(player["aircraft"], player["aircraft"]),
        "role": meta.get("role", "Mission"),
        "features": features(data),
        "date": meta["date"],
        "start_time": meta["start_time"],
        "objective": data["objectives"].get("primary", ""),
        "hook": (data["narrative"].get("hook") or "").strip(),
        "teaser": teaser,
        "campaign": camp["title"] if camp else "Standalone",
        "campaign_id": camp["id"] if camp else "",
        "chapter": f"{camp['title']} · {camp['chapter']}/{camp['of']}" if camp else "",
        "miz": miz_path(data, hangar).relative_to(hangar).as_posix(),
        "kneeboards": sorted(p.name for p in (hangar / meta["id"] / "kneeboard").glob("*.png")),
    }


def build(missions: list[dict], hangar: Path, campaigns: list[dict] = ()) -> list[Path]:
    from .build_campaign import summary
    cards = sorted((card(m, hangar) for m in missions), key=lambda c: (str(c["date"]), c["id"]))  # story order
    filters = [("campaign", "Campaign", [c["title"] for c in campaigns] + (["Standalone"] if any(not c["campaign_id"] for c in cards) else [])),
               ("aircraft", "Aircraft", sorted({c["aircraft_type"] for c in cards})),
               ("role", "Mission type", sorted({c["role"] for c in cards})),
               ("features", "Features", sorted({f for c in cards for f in c["features"]}))]
    by_id = {c["id"]: c for c in cards}
    sections = []
    for c in campaigns:  # one section per campaign, chapters in order
        sm = summary(c, missions)
        sections.append({"key": f"c-{c['id']}", "category": sm["category"], "heading": f"{c['title']} campaign",
                         "blurb": f"{sm['subtitle']} {sm['count']} chapters, {sm['first']} to {sm['last']}.".strip(),
                         "link": f"campaigns/{c['id']}/index.html", "missions": [by_id[ch["mission"]] for ch in c["chapters"]]})
    for cat, heading, blurb in (
            ("operational", "Standalone operations", "The Black Sea missions, to fly in any order. Briefings carry only what the squadron knows, and the sim decides the rest."),
            ("training", "Standalone training", "Syllabus events. Everything is briefed as it is: training rules, grade sheet, range players.")):
        group = [m for m in cards if m["category"] == cat and not m["campaign_id"]]
        if group:
            sections.append({"key": cat, "category": cat, "heading": heading, "blurb": blurb, "link": "", "missions": group})
    summaries = [summary(c, missions) for c in campaigns]
    hangar.mkdir(parents=True, exist_ok=True)
    out = []
    for name in ("index.html", "README.md"):
        path = hangar / name
        path.write_text(env().get_template(f"hangar.{name.split('.')[1]}.j2").render(
            missions=cards, filters=filters, sections=sections, campaigns=summaries))
        out.append(path)
    return out
