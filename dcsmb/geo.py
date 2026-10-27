"""Lat/lon <-> DCS map coordinates, using pydcs's own terrain projection."""
from dcs import mapping
from dcs.terrain import Terrain

FT = 0.3048
KTS = 1.852  # km/h per knot
NM = 1852.0


def point(terrain: Terrain, obj: dict) -> mapping.Point:
    return mapping.Point.from_latlng(mapping.LatLng(obj["lat"], obj["lon"]), terrain)
