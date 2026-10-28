"""python -m dcsmb build [missions/<name> ...] [--no-kneeboard]

With no mission dirs, builds every mission under missions/. The hangar index
(hangar/index.html and hangar/README.md) is always regenerated from all missions.
"""
import argparse
import shutil
import sys
from pathlib import Path

from . import build_campaign, build_director, build_hangar, build_html, build_miz, build_slides, kneeboard, schema

ROOT = Path(__file__).resolve().parent.parent
MISSIONS = ROOT / "missions"
CAMPAIGNS = ROOT / "campaigns"
HANGAR = ROOT / "hangar"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="dcsmb")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build .miz, briefing, slide deck and kneeboard pages into hangar/")
    b.add_argument("mission_dirs", type=Path, nargs="*", help="default: every folder in missions/")
    b.add_argument("--no-kneeboard", action="store_true", help="skip PNG rendering (no Chromium needed)")
    args = ap.parse_args(argv)

    all_dirs = sorted(p.parent for p in MISSIONS.glob("*/mission.yaml"))
    targets = [d.resolve() for d in args.mission_dirs] or all_dirs

    missions, failed = {}, False
    for d in all_dirs + [t for t in targets if t not in all_dirs]:
        try:
            missions[d] = schema.load(d)
        except schema.MissionError as e:
            print(f"{d.relative_to(ROOT)}/mission.yaml has problems:\n{e}", file=sys.stderr)
            failed = True
    if failed:
        return 1
    try:
        campaigns = schema.load_campaigns(CAMPAIGNS, list(missions.values()))
    except schema.MissionError as e:
        print(f"campaigns have problems:\n{e}", file=sys.stderr)
        return 1

    for d in targets:
        data = missions[d]
        out = HANGAR / data["meta"]["id"]
        pages = [] if args.no_kneeboard else kneeboard.build(data, out / "kneeboard")
        html = build_html.build(data, out / "briefing.html")
        deck = build_slides.build(data, out / "slides.html")
        director = build_director.build(data, out / "director.html")
        miz = build_campaign.miz_path(data, HANGAR)
        build_miz.build(data, miz, pages)
        for p in [miz, html, deck, director, *pages]:
            print(f"wrote {p.relative_to(ROOT)}")

    ids = {d["meta"]["id"] for d in missions.values()}
    for old in HANGAR.glob("*/briefing.html"):  # renders of missions that no longer exist
        if old.parent.name not in ids:
            shutil.rmtree(old.parent)
            print(f"removed {old.parent.relative_to(ROOT)}")
    for old in (HANGAR / "campaigns").glob("*/"):
        if old.name not in {c["id"] for c in campaigns}:
            shutil.rmtree(old)
            print(f"removed {old.relative_to(ROOT)}")
    for c in campaigns:
        for p in build_campaign.build(c, missions.values(), HANGAR):
            print(f"wrote {p.relative_to(ROOT)}")
    for p in build_hangar.build(list(missions.values()), HANGAR, campaigns):
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
