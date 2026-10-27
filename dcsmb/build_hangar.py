"""Hangar index: hangar/index.html (open locally) and hangar/README.md (renders on GitHub)."""
from __future__ import annotations

from pathlib import Path

from .build_html import env

AIRCRAFT_NAMES = {"FA_18C_hornet": "F/A-18C Hornet", "F_16C_50": "F-16C Viper", "A_10C_2": "A-10C II",
                  "MiG_29S": "MiG-29S", "E_3A": "E-3A"}


def card(data: dict, hangar: Path) -> dict:
    meta, player = data["meta"], next(f for f in data["flights"] if f.get("player"))
    teaser = data["narrative"]["backstory"].strip().split("\n\n")[0].replace("\n", " ")
    return {
        "id": meta["id"],
        "operation": data["narrative"].get("operation", meta["title"]),
        "title": meta.get("subtitle") or meta["title"],
        "theater": meta["theater"].title(),
        "aircraft": f"{player.get('count', 1)}× {AIRCRAFT_NAMES.get(player['aircraft'], player['aircraft'])}",
        "date": meta["date"],
        "start_time": meta["start_time"],
        "objective": data["objectives"].get("primary", ""),
        "hook": (data["narrative"].get("hook") or "").strip(),
        "teaser": teaser,
        "kneeboards": sorted(p.name for p in (hangar / meta["id"] / "kneeboard").glob("*.png")),
    }


def build(missions: list[dict], hangar: Path) -> list[Path]:
    cards = sorted((card(m, hangar) for m in missions), key=lambda c: (str(c["date"]), c["id"]))  # campaign order
    hangar.mkdir(parents=True, exist_ok=True)
    out = []
    for name in ("index.html", "README.md"):
        path = hangar / name
        path.write_text(env().get_template(f"hangar.{name.split('.')[1]}.j2").render(missions=cards))
        out.append(path)
    return out
