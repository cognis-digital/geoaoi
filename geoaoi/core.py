"""GEOAOI core engine — stdlib-only geospatial AOI helper.

Provides:
  * Bounding-box computation from coordinate logs.
  * Geofence (point-in-polygon + radius) membership checks.
  * Change-event diffs between two coordinate logs (enter/exit/move).

All math uses the WGS84 great-circle (haversine) distance and a
ray-casting point-in-polygon test. No third-party dependencies.
"""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass, field, asdict
from typing import Iterable, Sequence

EARTH_RADIUS_M = 6_371_008.8  # IUGG mean Earth radius, meters


# --------------------------------------------------------------------------- #
# Data types
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Point:
    """A single timestamped observation."""

    ident: str
    lat: float
    lon: float
    ts: str = ""

    def validate(self) -> None:
        if not (-90.0 <= self.lat <= 90.0):
            raise ValueError(f"latitude out of range for {self.ident!r}: {self.lat}")
        if not (-180.0 <= self.lon <= 180.0):
            raise ValueError(f"longitude out of range for {self.ident!r}: {self.lon}")


@dataclass
class BBox:
    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float
    count: int = 0

    @property
    def center(self) -> tuple[float, float]:
        return ((self.min_lat + self.max_lat) / 2.0, (self.min_lon + self.max_lon) / 2.0)

    @property
    def width_m(self) -> float:
        c_lat = self.center[0]
        return haversine_m(c_lat, self.min_lon, c_lat, self.max_lon)

    @property
    def height_m(self) -> float:
        c_lon = self.center[1]
        return haversine_m(self.min_lat, c_lon, self.max_lat, c_lon)

    def to_dict(self) -> dict:
        d = asdict(self)
        clat, clon = self.center
        d["center_lat"] = round(clat, 7)
        d["center_lon"] = round(clon, 7)
        d["width_m"] = round(self.width_m, 2)
        d["height_m"] = round(self.height_m, 2)
        return d


@dataclass
class Geofence:
    """A geofence is either a polygon (>=3 vertices) or a center+radius circle."""

    name: str
    polygon: list[tuple[float, float]] = field(default_factory=list)  # (lat, lon)
    center: tuple[float, float] | None = None
    radius_m: float = 0.0

    def contains(self, lat: float, lon: float) -> bool:
        if self.center is not None and self.radius_m > 0:
            return haversine_m(self.center[0], self.center[1], lat, lon) <= self.radius_m
        if len(self.polygon) >= 3:
            return point_in_polygon(lat, lon, self.polygon)
        raise ValueError(f"geofence {self.name!r} has neither valid polygon nor circle")


# --------------------------------------------------------------------------- #
# Geodesy primitives
# --------------------------------------------------------------------------- #
def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters between two WGS84 points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def point_in_polygon(lat: float, lon: float, polygon: Sequence[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon. Polygon is a list of (lat, lon) vertices.

    Treats lat as Y and lon as X. Boundary points count as inside.
    """
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        # On-edge / on-vertex check (cheap boundary inclusion).
        if _on_segment(lat, lon, polygon[i], polygon[j]):
            return True
        intersect = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / (yj - yi) + xi
        )
        if intersect:
            inside = not inside
        j = i
    return inside


def _on_segment(lat: float, lon: float, a: tuple[float, float], b: tuple[float, float]) -> bool:
    ay, ax = a
    by, bx = b
    cross = (bx - ax) * (lat - ay) - (by - ay) * (lon - ax)
    if abs(cross) > 1e-12:
        return False
    return min(ax, bx) - 1e-12 <= lon <= max(ax, bx) + 1e-12 and \
        min(ay, by) - 1e-12 <= lat <= max(ay, by) + 1e-12


# --------------------------------------------------------------------------- #
# Engine functions
# --------------------------------------------------------------------------- #
def compute_bbox(points: Iterable[Point]) -> BBox:
    pts = list(points)
    if not pts:
        raise ValueError("cannot compute bounding box of empty point set")
    lats = [p.lat for p in pts]
    lons = [p.lon for p in pts]
    return BBox(min(lats), min(lons), max(lats), max(lons), count=len(pts))


def geofence_check(points: Iterable[Point], fence: Geofence) -> list[dict]:
    """Return per-point membership results for a geofence."""
    results: list[dict] = []
    for p in points:
        p.validate()
        inside = fence.contains(p.lat, p.lon)
        row = {"ident": p.ident, "ts": p.ts, "lat": p.lat, "lon": p.lon, "inside": inside}
        if fence.center is not None and fence.radius_m > 0:
            row["distance_m"] = round(
                haversine_m(fence.center[0], fence.center[1], p.lat, p.lon), 2
            )
        results.append(row)
    return results


def diff_events(
    before: Iterable[Point],
    after: Iterable[Point],
    move_threshold_m: float = 50.0,
) -> list[dict]:
    """Diff two coordinate logs keyed by ident -> enter/exit/move/static events."""
    b = {p.ident: p for p in before}
    a = {p.ident: p for p in after}
    events: list[dict] = []
    for ident in sorted(set(b) | set(a)):
        if ident in a and ident not in b:
            p = a[ident]
            events.append({"ident": ident, "event": "enter", "lat": p.lat, "lon": p.lon, "moved_m": None})
        elif ident in b and ident not in a:
            p = b[ident]
            events.append({"ident": ident, "event": "exit", "lat": p.lat, "lon": p.lon, "moved_m": None})
        else:
            pb, pa = b[ident], a[ident]
            d = haversine_m(pb.lat, pb.lon, pa.lat, pa.lon)
            events.append(
                {
                    "ident": ident,
                    "event": "move" if d >= move_threshold_m else "static",
                    "lat": pa.lat,
                    "lon": pa.lon,
                    "moved_m": round(d, 2),
                }
            )
    return events


# --------------------------------------------------------------------------- #
# Parsing helpers
# --------------------------------------------------------------------------- #
def parse_points_csv(text: str) -> list[Point]:
    """Parse a coordinate log CSV.

    Header is required and must contain lat/lon columns. Recognized
    column names: ident/id/name, lat/latitude, lon/lng/longitude, ts/time/timestamp.
    """
    # Strip a UTF-8 BOM if present (common in Windows-exported logs).
    text = text.lstrip("﻿")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("CSV has no header row")
    cols = {c.strip().lower(): c for c in reader.fieldnames}

    def pick(*names: str) -> str | None:
        for n in names:
            if n in cols:
                return cols[n]
        return None

    lat_c = pick("lat", "latitude")
    lon_c = pick("lon", "lng", "long", "longitude")
    id_c = pick("ident", "id", "name", "callsign")
    ts_c = pick("ts", "time", "timestamp")
    if lat_c is None or lon_c is None:
        raise ValueError("CSV must have latitude and longitude columns")

    out: list[Point] = []
    for i, row in enumerate(reader):
        try:
            lat = float(row[lat_c])
            lon = float(row[lon_c])
        except (KeyError, ValueError) as exc:
            raise ValueError(f"row {i + 1}: bad coordinate: {exc}") from exc
        ident = (row.get(id_c) if id_c else None) or f"row{i + 1}"
        ts = (row.get(ts_c) if ts_c else "") or ""
        p = Point(ident=ident.strip(), lat=lat, lon=lon, ts=ts.strip())
        p.validate()
        out.append(p)
    return out


def parse_polygon(spec: str) -> list[tuple[float, float]]:
    """Parse 'lat,lon;lat,lon;...' into a list of (lat, lon) vertices."""
    verts: list[tuple[float, float]] = []
    for pair in spec.split(";"):
        pair = pair.strip()
        if not pair:
            continue
        a, b = pair.split(",")
        verts.append((float(a), float(b)))
    if len(verts) < 3:
        raise ValueError("polygon needs at least 3 vertices")
    return verts
