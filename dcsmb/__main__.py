"""python -m dcsmb build missions/<name> [--no-kneeboard]"""
import argparse
import sys
from pathlib import Path

from . import build_html, build_miz, kneeboard, schema

ROOT = Path(__file__).resolve().parent.parent


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="dcsmb")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build .miz, briefing.html and kneeboard pages")
    b.add_argument("mission_dir", type=Path)
    b.add_argument("--no-kneeboard", action="store_true", help="skip PNG rendering (no Chromium needed)")
    args = ap.parse_args(argv)

    try:
        data = schema.load(args.mission_dir)
    except schema.MissionError as e:
        print(f"mission.yaml has problems:\n{e}", file=sys.stderr)
        return 1

    out = ROOT / "out" / data["meta"]["id"]
    pages = [] if args.no_kneeboard else kneeboard.build(data, out / "kneeboard")
    html = build_html.build(data, out / "briefing.html")
    miz = out / f"{data['meta']['id']}.miz"
    build_miz.build(data, miz, pages)
    print(f"wrote {miz.relative_to(ROOT)}")
    print(f"wrote {html.relative_to(ROOT)}")
    for p in pages:
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
