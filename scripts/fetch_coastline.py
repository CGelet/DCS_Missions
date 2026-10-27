"""Fetch the coastline for a theater from OpenStreetMap and save it simplified.

Used by the slide decks to draw offline map slides. Only needs re-running when a
new theater is added:

    python scripts/fetch_coastline.py caucasus 41.5 39.5 43.6 42.0
    python scripts/fetch_coastline.py caucasus ... --from-file overpass.json   # reuse a saved response

Writes dcsmb/data/coast_<theater>.json: a list of polylines of [lat, lon].
Coastline data (c) OpenStreetMap contributors, ODbL.
"""
import argparse
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "dcsmb" / "data"
OVERPASS = "https://overpass-api.de/api/interpreter"
TOLERANCE_M = 150


def fetch(s, w, n, e) -> dict:
    q = f'[out:json][timeout:90];way["natural"="coastline"]({s},{w},{n},{e});out geom;'
    req = urllib.request.Request(OVERPASS, data=urllib.parse.urlencode({"data": q}).encode(),
                                 headers={"User-Agent": "dcsmb-coastline"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def stitch(ways: list[list[tuple]]) -> list[list[tuple]]:
    """Join ways that share endpoints into longer polylines."""
    lines = [list(w) for w in ways]
    merged = True
    while merged:
        merged = False
        for i, a in enumerate(lines):
            for j, b in enumerate(lines):
                if i != j and a[-1] == b[0]:
                    lines[i] = a + b[1:]
                    del lines[j]
                    merged = True
                    break
            if merged:
                break
    return lines


def simplify(pts: list[tuple], tol_m: float) -> list[tuple]:
    """Douglas-Peucker on a local equirectangular projection."""
    if len(pts) < 3:
        return pts
    k = math.cos(math.radians(pts[0][0]))
    xy = [(p[1] * 111_320 * k, p[0] * 110_540) for p in pts]

    def dist(p, a, b):
        (x, y), (x1, y1), (x2, y2) = p, a, b
        dx, dy = x2 - x1, y2 - y1
        if dx == dy == 0:
            return math.hypot(x - x1, y - y1)
        t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
        return math.hypot(x - x1 - t * dx, y - y1 - t * dy)

    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        best, idx = 0.0, None
        for m in range(i + 1, j):
            d = dist(xy[m], xy[i], xy[j])
            if d > best:
                best, idx = d, m
        if idx is not None and best > tol_m:
            keep[idx] = True
            stack += [(i, idx), (idx, j)]
    return [p for p, k_ in zip(pts, keep) if k_]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("theater")
    ap.add_argument("bbox", nargs=4, type=float, metavar=("S", "W", "N", "E"))
    ap.add_argument("--from-file", type=Path)
    args = ap.parse_args()

    data = json.loads(args.from_file.read_text()) if args.from_file else fetch(*args.bbox)
    ways = [[(round(g["lat"], 5), round(g["lon"], 5)) for g in e["geometry"]] for e in data["elements"]]
    lines = [simplify(l, TOLERANCE_M) for l in stitch(ways)]
    lines = [[[round(a, 4), round(b, 4)] for a, b in l] for l in lines if len(l) >= 2]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"coast_{args.theater}.json"
    out.write_text(json.dumps(lines, separators=(",", ":")))
    print(f"wrote {out} ({len(lines)} lines, {sum(map(len, lines))} points)")


if __name__ == "__main__":
    main()
