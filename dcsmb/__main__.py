"""python -m dcsmb build [missions/<name> ...] [--no-kneeboard]

With no mission dirs, builds every mission under missions/. The hangar index
(hangar/index.html and hangar/README.md) is always regenerated from all missions.
"""
import argparse
import sys
from pathlib import Path

from . import build_hangar, build_html, build_miz, kneeboard, schema

ROOT = Path(__file__).resolve().parent.parent
MISSIONS = ROOT / "missions"
HANGAR = ROOT / "hangar"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="dcsmb")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build .miz, briefing.html and kneeboard pages into hangar/")
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

    for d in targets:
        data = missions[d]
        out = HANGAR / data["meta"]["id"]
        pages = [] if args.no_kneeboard else kneeboard.build(data, out / "kneeboard")
        html = build_html.build(data, out / "briefing.html")
        miz = out / f"{data['meta']['id']}.miz"
        build_miz.build(data, miz, pages)
        for p in [miz, html, *pages]:
            print(f"wrote {p.relative_to(ROOT)}")

    for p in build_hangar.build(list(missions.values()), HANGAR):
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
