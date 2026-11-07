"""Route options from third-party routing APIs.

Primary: Valhalla (public OSM server) with the *truck* costing model, so the truck's gross
weight is respected (weight-restricted roads, truck speeds). Fallback: the public OSRM
demo server (car profile) with a truck speed cap applied.

Routing APIs often return fewer than 3 alternatives, so we fill the gap:
  1. Ask Valhalla for its own alternates.
  2. Ask OSRM for its alternatives (it searches differently and usually finds 2–3).
     For each one that differs from what we have, pick a point in the middle of its
     *distinct* stretch and ask Valhalla for a truck route through that point, with a
     heading so the truck passes straight through (no U-turn spur). Each leg is a
     separate request because the public server caps multi-stop paths at 1,500 km.
  3. Still short? Same idea with points offset to either side of the O–D line, then
     re-route with a small exclusion zone dropped on an existing route.
Candidates are kept only if genuinely different (< 80% overlap with every route already
chosen) and not absurdly long (≤ 1.6× the fastest drive time).
If Valhalla can't route the trip at all (e.g. > 1,500 km), OSRM routes are used directly.
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from dataclasses import dataclass, field

import requests
from django.conf import settings

from .geo import LatLon, METERS_PER_MILE, cumulative_m, decode_polyline, haversine_m, point_at

log = logging.getLogger(__name__)

TRUCK_MAX_SPEED_MPH = 65.0  # applied to car-profile durations (OSRM fallback)
TRACTOR_TRAILER_TARE_LBS = 35_000  # empty tractor + 53' trailer, added to load for gross weight
LBS_PER_TONNE = 2204.62
MAX_DETOUR_RATIO = 1.6
MAX_OVERLAP = 0.8
TARGET_ROUTES = 3
MAX_EXTRA_REQUESTS = 9  # bounds latency; each guided route costs 2 requests
EXCLUSION_RADIUS_M = 1_500  # the public server caps exclusion polygons at 10 km circumference
CELL_DEG = 0.02  # ~1.4 mi cells for overlap tests

ROUTING_ERRORS = (requests.RequestException, KeyError, ValueError, IndexError)


class RoutingError(Exception):
    pass


@dataclass
class Route:
    coords: list[LatLon]
    cum_m: list[float]
    cum_drive_s: list[float]
    roads: list[str] = field(default_factory=list)
    source: str = ""

    @property
    def distance_m(self) -> float:
        return self.cum_m[-1]

    @property
    def drive_s(self) -> float:
        return self.cum_drive_s[-1]


def stitch(legs: list[Route]) -> Route:
    """Join consecutive legs (each starting where the previous ended) into one route."""
    coords, drive = list(legs[0].coords), list(legs[0].cum_drive_s)
    for leg in legs[1:]:
        coords.extend(leg.coords[1:])
        offset = drive[-1]
        drive.extend(offset + t for t in leg.cum_drive_s[1:])
    roads: Counter = Counter()
    for leg in legs:
        for rank, name in enumerate(leg.roads):
            roads[name] += leg.distance_m / (rank + 1)
    return Route(coords, cumulative_m(coords), drive, [n for n, _ in roads.most_common(2)], legs[0].source)


def bearing_deg(a: LatLon, b: LatLon) -> float:
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlon = math.radians(b[1] - a[1])
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _octagon(center: LatLon, radius_m: float) -> list[list[float]]:
    """Closed [lon, lat] ring approximating a circle (Valhalla's exclude_polygons format)."""
    lat, lon = center
    dlat = radius_m / 111_320
    dlon = dlat / max(math.cos(math.radians(lat)), 0.2)
    ring = [[lon + dlon * math.cos(k * math.pi / 4), lat + dlat * math.sin(k * math.pi / 4)] for k in range(8)]
    return ring + [ring[0]]


# --- Valhalla ----------------------------------------------------------------------------


class ValhallaProvider:
    name = "valhalla-truck"

    def __init__(self, session: requests.Session, gross_lbs: float):
        self.session = session
        self.url = settings.VALHALLA_URL
        self.gross_t = min(gross_lbs / LBS_PER_TONNE, 60.0)

    def routes(self, a: LatLon, b: LatLon, alternates: int = 0,
               heading_a: float | None = None, heading_b: float | None = None,
               exclude: LatLon | None = None) -> list[Route]:
        locations = [{"lat": a[0], "lon": a[1]}, {"lat": b[0], "lon": b[1]}]
        for loc, heading in zip(locations, (heading_a, heading_b)):
            if heading is not None:
                loc.update(heading=round(heading), heading_tolerance=45)
        body = {
            "locations": locations,
            "costing": "truck",
            "costing_options": {"truck": {"weight": round(self.gross_t, 2)}},
            "units": "miles",
            "directions_type": "maneuvers",
            "narrative": False,
        }
        if alternates:
            body["alternates"] = alternates
        if exclude:
            body["exclude_polygons"] = [_octagon(exclude, EXCLUSION_RADIUS_M)]
        resp = self.session.post(self.url, json=body, timeout=settings.HTTP_TIMEOUT_S)
        if resp.status_code != 200:
            raise RoutingError(f"Valhalla HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        trips = [data["trip"]] + [alt["trip"] for alt in data.get("alternates", [])]
        return [self._parse(t) for t in trips]

    def through(self, origin: LatLon, via: LatLon, heading: float, dest: LatLon) -> Route:
        """Truck route forced through `via` while travelling at `heading`."""
        first = self.routes(origin, via, heading_b=heading)[0]
        second = self.routes(via, dest, heading_a=heading)[0]
        return stitch([first, second])

    def _parse(self, trip: dict) -> Route:
        coords: list[LatLon] = []
        drive: list[float] = []
        roads: Counter = Counter()
        for leg in trip["legs"]:
            shape = decode_polyline(leg["shape"], 6)
            cum = cumulative_m(shape)
            leg_drive = [0.0] * len(shape)
            for m in leg["maneuvers"]:
                b, e = m["begin_shape_index"], m["end_shape_index"]
                span = cum[e] - cum[b]
                for i in range(b + 1, e + 1):  # spread maneuver time by distance
                    share = (cum[i] - cum[i - 1]) / span if span else 1.0 / max(e - b, 1)
                    leg_drive[i] = leg_drive[i - 1] + m["time"] * share
                for name in m.get("street_names", [])[:1]:
                    roads[name] += m.get("length", 0.0)
            offset = drive[-1] if drive else 0.0
            start = 1 if coords else 0  # legs share their boundary vertex
            coords.extend(shape[start:])
            drive.extend(offset + t for t in leg_drive[start:])
        return Route(coords, cumulative_m(coords), drive, [n for n, _ in roads.most_common(2)], self.name)


# --- OSRM ----------------------------------------------------------------------------------


class OsrmProvider:
    name = "osrm"

    def __init__(self, session: requests.Session):
        self.session = session
        self.url = settings.OSRM_URL

    def routes(self, waypoints: list[LatLon], alternates: int = 0) -> list[Route]:
        path = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in waypoints)
        params = {
            "overview": "full",
            "geometries": "geojson",
            "annotations": "duration",
            "steps": "true",  # needed for the leg summary (main road names)
            "alternatives": str(alternates) if alternates else "false",
        }
        resp = self.session.get(f"{self.url}/{path}", params=params, timeout=settings.HTTP_TIMEOUT_S)
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code != 200 or data.get("code") != "Ok":
            raise RoutingError(f"OSRM HTTP {resp.status_code}: {data.get('message', resp.text[:200])}")
        return [self._parse(r) for r in data["routes"]]

    def _parse(self, r: dict) -> Route:
        coords = [(lat, lon) for lon, lat in r["geometry"]["coordinates"]]
        cum = cumulative_m(coords)
        seg = [d for leg in r["legs"] for d in leg["annotation"]["duration"]]
        if len(seg) != len(coords) - 1:  # defensive: spread the total by distance
            seg = [(cum[i + 1] - cum[i]) / cum[-1] * r["duration"] for i in range(len(coords) - 1)]
        cap_mps = TRUCK_MAX_SPEED_MPH * METERS_PER_MILE / 3600
        drive = [0.0]
        for i, d in enumerate(seg):
            drive.append(drive[-1] + max(d, (cum[i + 1] - cum[i]) / cap_mps))
        roads = [s.strip() for leg in r["legs"] for s in leg.get("summary", "").split(",") if s.strip()]
        return Route(coords, cum, drive, roads[:2], self.name)


# --- Distinctness --------------------------------------------------------------------------


def route_cells(route: Route) -> set[tuple[int, int]]:
    """Grid cells touched by the route, densified (~1 km) so long segments aren't skipped."""
    cells = set()
    for a, b in zip(route.coords, route.coords[1:]):
        steps = max(1, int(haversine_m(a, b) / 1000))
        for k in range(steps + 1):
            t = k / steps
            cells.add((round((a[0] + t * (b[0] - a[0])) / CELL_DEG),
                       round((a[1] + t * (b[1] - a[1])) / CELL_DEG)))
    return cells


def _near(cell: tuple[int, int], cells: set) -> bool:
    y, x = cell
    return any((y + dy, x + dx) in cells for dy in (-1, 0, 1) for dx in (-1, 0, 1))


def overlap(candidate: Route, existing: set[tuple[int, int]]) -> float:
    cand = route_cells(candidate)
    return sum(_near(c, existing) for c in cand) / len(cand) if cand else 1.0


def select_distinct(chosen: list[Route], candidates: list[Route], target: int = TARGET_ROUTES) -> list[Route]:
    out = list(chosen)
    cell_sets = [route_cells(r) for r in out]
    fastest = min((r.drive_s for r in out + candidates), default=0)
    for r in candidates:
        if len(out) >= target:
            break
        if fastest and r.drive_s > MAX_DETOUR_RATIO * fastest:
            continue
        if any(overlap(r, cs) >= MAX_OVERLAP for cs in cell_sets):
            continue
        out.append(r)
        cell_sets.append(route_cells(r))
    return out


def distinct_midpoint(candidate: Route, chosen: list[Route]) -> tuple[LatLon, float] | None:
    """Middle of the longest stretch of `candidate` away from all chosen routes, with the
    direction of travel there. None if the candidate has no meaningfully distinct stretch."""
    taken = set().union(*(route_cells(r) for r in chosen)) if chosen else set()
    best_len, best = 0.0, None
    run_start = None
    last = len(candidate.coords) - 1
    for i, p in enumerate(candidate.coords):
        free = not _near((round(p[0] / CELL_DEG), round(p[1] / CELL_DEG)), taken)
        if free and run_start is None:
            run_start = i
        if run_start is not None and (not free or i == last):
            length = candidate.cum_m[i] - candidate.cum_m[run_start]
            if length > best_len:
                best_len, best = length, (run_start, i)
            run_start = None
    if best is None or best_len < 5_000:
        return None
    mid_m = (candidate.cum_m[best[0]] + candidate.cum_m[best[1]]) / 2
    p = point_at(candidate.coords, candidate.cum_m, mid_m)
    ahead = point_at(candidate.coords, candidate.cum_m, mid_m + 500)
    return p, bearing_deg(p, ahead)


def offset_guides(origin: LatLon, dest: LatLon) -> list[Route]:
    """Pseudo-routes bowing out to either side of the O–D line. Only used to derive via
    points when the routing APIs offer no real alternative."""
    mid_lat = (origin[0] + dest[0]) / 2
    kx = math.cos(math.radians(mid_lat))  # degrees of lon shrink away from the equator
    dx, dy = (dest[1] - origin[1]) * kx, dest[0] - origin[0]
    length = math.hypot(dx, dy) or 1e-9
    px, py = -dy / length, dx / length  # unit perpendicular in local planar coords
    guides = []
    for frac in (0.15, -0.15, 0.3, -0.3):
        via = (mid_lat + py * frac * length, (origin[1] + dest[1]) / 2 + px * frac * length / kx)
        coords = [origin, via, dest]
        guides.append(Route(coords, cumulative_m(coords), [0.0, 0.0, 0.0]))
    return guides


# --- Orchestration -------------------------------------------------------------------------


def _valhalla_routes(valhalla: ValhallaProvider, osrm: OsrmProvider, origin: LatLon, dest: LatLon) -> list[Route]:
    routes = select_distinct([], valhalla.routes(origin, dest, alternates=TARGET_ROUTES - 1))
    if len(routes) >= TARGET_ROUTES:
        return routes
    try:
        osrm_guides = osrm.routes([origin, dest], alternates=TARGET_ROUTES)
    except (RoutingError, *ROUTING_ERRORS) as exc:
        log.info("OSRM guide routes unavailable: %s", exc)
        osrm_guides = []

    def guided(guide: Route):
        target = distinct_midpoint(guide, routes)
        if target is None:
            return None  # nothing distinct to aim for; costs no request
        return 2, lambda: [valhalla.through(origin, target[0], target[1], dest)]

    def excluded(frac: float):
        fastest = routes[0]
        block = point_at(fastest.coords, fastest.cum_m, frac * fastest.distance_m)
        return 1, lambda: valhalla.routes(origin, dest, exclude=block)

    # Most promising first: real alternatives, a blocked midpoint, then synthetic detours.
    attempts = [lambda g=g: guided(g) for g in osrm_guides]
    attempts.append(lambda: excluded(0.5))
    attempts += [lambda g=g: guided(g) for g in offset_guides(origin, dest)]
    attempts += [lambda: excluded(0.3), lambda: excluded(0.7)]

    budget = MAX_EXTRA_REQUESTS
    for make in attempts:
        if len(routes) >= TARGET_ROUTES:
            break
        planned = make()
        if planned is None or planned[0] > budget:
            continue
        cost, run = planned
        budget -= cost
        try:
            routes = select_distinct(routes, run())
        except (RoutingError, *ROUTING_ERRORS) as exc:
            log.info("alternative route request failed: %s", exc)
    return routes


def _osrm_routes(osrm: OsrmProvider, origin: LatLon, dest: LatLon) -> list[Route]:
    routes = select_distinct([], osrm.routes([origin, dest], alternates=TARGET_ROUTES))
    for guide in offset_guides(origin, dest):
        if len(routes) >= TARGET_ROUTES:
            break
        try:
            routes = select_distinct(routes, osrm.routes([origin, guide.coords[1], dest]))
        except (RoutingError, *ROUTING_ERRORS) as exc:
            log.info("OSRM detour failed: %s", exc)
    return routes


def plan_routes(origin: LatLon, dest: LatLon, load_lbs: float) -> tuple[list[Route], str, list[str]]:
    """Returns up to 3 distinct routes (fastest first), the provider used, and warnings."""
    session = requests.Session()
    session.headers["User-Agent"] = settings.HTTP_USER_AGENT
    valhalla = ValhallaProvider(session, load_lbs + TRACTOR_TRAILER_TARE_LBS)
    osrm = OsrmProvider(session)
    warnings: list[str] = []
    try:
        routes, provider = _valhalla_routes(valhalla, osrm, origin, dest), valhalla.name
    except (RoutingError, *ROUTING_ERRORS) as exc:
        log.warning("Valhalla truck routing failed, falling back to OSRM: %s", exc)
        try:
            routes, provider = _osrm_routes(osrm, origin, dest), osrm.name
        except (RoutingError, *ROUTING_ERRORS) as exc2:
            log.warning("OSRM fallback failed too: %s", exc2)
            raise RoutingError("Couldn't find a drivable route between these places. "
                               "Check both locations are reachable by road.") from exc2
        warnings.append("Truck routing is unavailable for this trip (the public truck router only "
                        "accepts trips up to ~930 mi straight-line), so car routing with a 65 mph truck speed cap is used.")
    if len(routes) < TARGET_ROUTES:
        warnings.append(f"Only {len(routes)} distinct route(s) found between these points.")
    routes.sort(key=lambda r: r.drive_s)
    return routes, provider, warnings
