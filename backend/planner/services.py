"""Trip planning: routes -> checkpoints at the truck's ETA -> weather -> risk -> recommendation."""

from __future__ import annotations

from datetime import datetime

from .geo import METERS_PER_MILE, LatLon, point_at, simplify_indices
from .recommend import recommend, summarize
from .risk import assess
from .routing import Route, plan_routes
from .timeline import Timeline
from .weather import fetch_series, snap

INTERVALS_MI = (10, 25, 50)
ROUTE_IDS = ("A", "B", "C")
SIMPLIFY_DEG = 0.0007  # ~70 m; keeps the map light without visible corner cutting


def checkpoint_marks(total_mi: float, interval_mi: float) -> list[tuple[float, float]]:
    """(mile, miles_covered) for checkpoints at 0, I, 2I, … and the destination.

    Each checkpoint stands for the stretch halfway to its neighbours, so coverage sums to
    the route length exactly and Severe/High miles are true road miles.
    """
    marks = [i * interval_mi for i in range(int(total_mi // interval_mi) + 1)]
    if total_mi - marks[-1] > 1e-6:
        marks.append(total_mi)
    if len(marks) == 1:
        return [(0.0, total_mi)]
    out = []
    for i, m in enumerate(marks):
        lo = 0.0 if i == 0 else (marks[i - 1] + m) / 2
        hi = total_mi if i == len(marks) - 1 else (m + marks[i + 1]) / 2
        out.append((m, hi - lo))
    return out


def _route_payload(rid: str, route: Route, timeline: Timeline) -> dict:
    keep = simplify_indices(route.coords, SIMPLIFY_DEG)
    name = f"Route {rid}"
    return {
        "id": rid,
        "name": name,
        "via": route.roads,
        "geometry": [[round(route.coords[i][0], 5), round(route.coords[i][1], 5)] for i in keep],
        "vertex_mi": [round(route.cum_m[i] / METERS_PER_MILE, 2) for i in keep],
        "distance_mi": round(route.distance_m / METERS_PER_MILE, 1),
        "drive_s": round(route.drive_s),
        "travel_s": round(timeline.total_elapsed_s),
        "departure": timeline.departure.isoformat(),
        "arrival": timeline.arrival.isoformat(),
        "stops": [
            {
                "kind": s["kind"],
                "mi": round(s["dist_m"] / METERS_PER_MILE, 1),
                "lat": round(p[0], 5),
                "lon": round(p[1], 5),
                "start": s["start"].isoformat(),
                "duration_s": s["duration_s"],
            }
            for s in timeline.stop_events()
            for p in [point_at(route.coords, route.cum_m, s["dist_m"])]
        ],
    }


def plan_trip(origin: LatLon, dest: LatLon, departure: datetime, load_lbs: float,
              include_hos: bool = True) -> dict:
    routes, provider, warnings = plan_routes(origin, dest, load_lbs)
    timelines = [Timeline(r.cum_m, r.cum_drive_s, departure, include_hos) for r in routes]

    # 1. Sample every interval on every route; remember where and when the truck is.
    samples: list[dict[int, list[dict]]] = []
    all_points: list[LatLon] = []
    for route, tl in zip(routes, timelines):
        total_mi = route.distance_m / METERS_PER_MILE
        per_interval = {}
        for interval in INTERVALS_MI:
            cps = []
            for mile, cover in checkpoint_marks(total_mi, interval):
                dist_m = mile * METERS_PER_MILE
                lat, lon = point_at(route.coords, route.cum_m, dist_m)
                cps.append({"mi": mile, "cover_mi": cover, "lat": lat, "lon": lon, "eta": tl.eta(dist_m)})
                all_points.append((lat, lon))
            per_interval[interval] = cps
        samples.append(per_interval)

    # 2. One batched forecast fetch for every checkpoint of every route/interval.
    latest_arrival = max(tl.arrival for tl in timelines)
    series = fetch_series(all_points, departure, latest_arrival)

    # 3. Read the forecast at each checkpoint's ETA and classify it.
    payload_routes = []
    summaries = {interval: {} for interval in INTERVALS_MI}
    for rid, route, tl, per_interval in zip(ROUTE_IDS, routes, timelines, samples):
        body = _route_payload(rid, route, tl)
        body["checkpoints"] = {}
        body["summary"] = {}
        for interval, cps in per_interval.items():
            out = [_score(cp, series, load_lbs) for cp in cps]
            body["checkpoints"][str(interval)] = out
            s = summarize(out, tl.total_elapsed_s)
            summaries[interval][rid] = s
            body["summary"][str(interval)] = s.to_dict()
        payload_routes.append(body)

    names = {r["id"]: r["name"] for r in payload_routes}
    return {
        "provider": provider,
        "warnings": warnings,
        "load_lbs": load_lbs,
        "include_hos": include_hos,
        "intervals": list(INTERVALS_MI),
        "routes": payload_routes,
        "recommendation": {str(i): recommend(summaries[i], names) for i in INTERVALS_MI},
    }


def _score(cp: dict, series: dict, load_lbs: float) -> dict:
    s = series.get(snap((cp["lat"], cp["lon"])))
    reading = s.at(cp["eta"]) if s else None
    out = {
        "mi": round(cp["mi"], 1),
        "cover_mi": round(cp["cover_mi"], 2),
        "lat": round(cp["lat"], 5),
        "lon": round(cp["lon"], 5),
        "eta": cp["eta"].isoformat(),
    }
    if reading is None:  # beyond forecast horizon
        out.update(level=None, factor=None, wind=None, gust=None, rain=None, snow=None, temp=None, code=None)
        return out
    a = assess(reading.wind_mph, reading.rain_in_hr, reading.snow_in_hr, load_lbs)
    out.update(
        level=int(a.level),
        factor=a.factor,
        levels={"wind": int(a.wind), "rain": int(a.rain), "snow": int(a.snow)},
        wind=round(reading.wind_mph, 1),
        gust=round(reading.gust_mph, 1),
        rain=round(reading.rain_in_hr, 3),
        snow=round(reading.snow_in_hr, 2),
        temp=round(reading.temp_f),
        code=reading.code,
    )
    return out
