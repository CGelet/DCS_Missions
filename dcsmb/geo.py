"""Lat/lon <-> DCS map coordinates, using pydcs's own terrain projection."""
from dcs import mapping
from dcs.terrain import Caucasus, Nevada, Terrain

FT = 0.3048
KTS = 1.852  # km/h per knot
NM = 1852.0

# DCS maps the owner has. BOX is the map's lat/lon extent (from pydcs's terrain bounds, rounded in),
# so a typo like a positive Nevada longitude fails validation instead of putting a unit off the map.
THEATERS = {"caucasus": Caucasus, "nevada": Nevada}
BOX = {"caucasus": (39.6, 47.4, 27.7, 47.1), "nevada": (35.3, 38.3, -118.5, -112.6)}


def terrain_for(meta: dict) -> Terrain:
    return THEATERS[meta["theater"]]()


def point(terrain: Terrain, obj: dict) -> mapping.Point:
    return mapping.Point.from_latlng(mapping.LatLng(obj["lat"], obj["lon"]), terrain)
