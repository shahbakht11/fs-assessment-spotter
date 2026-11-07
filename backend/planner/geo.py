"""Small geometry helpers. Coordinates are (lat, lon) tuples in degrees."""

from __future__ import annotations

import math
from bisect import bisect_right

EARTH_RADIUS_M = 6_371_008.8
METERS_PER_MILE = 1609.344

LatLon = tuple[float, float]


def haversine_m(a: LatLon, b: LatLon) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def cumulative_m(coords: list[LatLon]) -> list[float]:
    out = [0.0]
    for a, b in zip(coords, coords[1:]):
        out.append(out[-1] + haversine_m(a, b))
    return out


def interpolate(values_at: list[float], values: list[float], x: float) -> float:
    """Linear interpolation of `values` (sampled at increasing `values_at`) at x, clamped."""
    if x <= values_at[0]:
        return values[0]
    if x >= values_at[-1]:
        return values[-1]
    i = bisect_right(values_at, x) - 1
    x0, x1 = values_at[i], values_at[i + 1]
    t = 0.0 if x1 == x0 else (x - x0) / (x1 - x0)
    return values[i] + t * (values[i + 1] - values[i])


def point_at(coords: list[LatLon], cum: list[float], dist_m: float) -> LatLon:
    if dist_m <= 0:
        return coords[0]
    if dist_m >= cum[-1]:
        return coords[-1]
    i = bisect_right(cum, dist_m) - 1
    seg = cum[i + 1] - cum[i]
    t = 0.0 if seg == 0 else (dist_m - cum[i]) / seg
    (la0, lo0), (la1, lo1) = coords[i], coords[i + 1]
    return (la0 + t * (la1 - la0), lo0 + t * (lo1 - lo0))


def simplify_indices(coords: list[LatLon], tolerance_deg: float) -> list[int]:
    """Douglas–Peucker (iterative) returning the kept vertex indices, in order."""
    n = len(coords)
    if n <= 2:
        return list(range(n))
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    tol2 = tolerance_deg * tolerance_deg
    while stack:
        start, end = stack.pop()
        (ay, ax), (by, bx) = coords[start], coords[end]
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        best, best_i = -1.0, -1
        for i in range(start + 1, end):
            py, px = coords[i]
            if seg2 == 0:
                d2 = (px - ax) ** 2 + (py - ay) ** 2
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
                d2 = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2
            if d2 > best:
                best, best_i = d2, i
        if best > tol2:
            keep[best_i] = True
            stack.append((start, best_i))
            stack.append((best_i, end))
    return [i for i, k in enumerate(keep) if k]


def decode_polyline(encoded: str, precision: int = 6) -> list[LatLon]:
    """Google encoded-polyline decoder (Valhalla uses precision 6)."""
    coords: list[LatLon] = []
    index = lat = lon = 0
    factor = 10**precision
    length = len(encoded)
    while index < length:
        for which in (0, 1):
            shift = result = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if which == 0:
                lat += delta
            else:
                lon += delta
        coords.append((lat / factor, lon / factor))
    return coords


# --- Web Mercator (the heatmap grid is uniform in Mercator so it overlays without warping)


def lat_to_merc_y(lat: float) -> float:
    lat = max(min(lat, 85.0), -85.0)
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def merc_y_to_lat(y: float) -> float:
    return math.degrees(2 * math.atan(math.exp(y)) - math.pi / 2)
