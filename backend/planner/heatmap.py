"""Weather heatmap along the trip corridor, hourly for 0–48 h after departure.

The grid is uniform in Web Mercator, so the client can paint one pixel per cell and
stretch the image over the map bounds without distortion. Only cells within
CORRIDOR_MI of a route are fetched; the rest are masked out.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from .geo import METERS_PER_MILE, LatLon, cumulative_m, lat_to_merc_y, merc_y_to_lat, point_at
from .risk import risk_score
from .weather import fetch_series, floor_hour, snap

HOURS = 48
CORRIDOR_MI = 45.0
MAX_CELLS = 320  # keeps one heatmap well inside Open-Meteo's free per-minute budget
MIN_SPACING_MI = 8.0
MILES_PER_DEG_LAT = 69.0


def _corridor_cells(routes: list[list[LatLon]], spacing_mi: float):
    lats = [p[0] for r in routes for p in r]
    lons = [p[1] for r in routes for p in r]
    pad_lat = (CORRIDOR_MI + 1.5 * spacing_mi) / MILES_PER_DEG_LAT  # room for the edge to fade out
    mid_lat = (min(lats) + max(lats)) / 2
    pad_lon = pad_lat / max(math.cos(math.radians(mid_lat)), 0.2)
    south, north = min(lats) - pad_lat, max(lats) + pad_lat
    west, east = min(lons) - pad_lon, max(lons) + pad_lon

    # Mercator cell size matching `spacing_mi` at the corridor's mid latitude.
    dx_deg = spacing_mi / (MILES_PER_DEG_LAT * math.cos(math.radians(mid_lat)))
    nx = max(2, math.ceil((east - west) / dx_deg) + 1)
    y0, y1 = lat_to_merc_y(south), lat_to_merc_y(north)
    dy_merc = math.radians(dx_deg)  # Mercator y and lon (in radians) share a scale
    ny = max(2, math.ceil((y1 - y0) / dy_merc) + 1)
    east = west + (nx - 1) * dx_deg
    y1 = y0 + (ny - 1) * dy_merc

    row_lat = [merc_y_to_lat(y1 - j * dy_merc) for j in range(ny)]  # row 0 = north
    col_lon = [west + i * dx_deg for i in range(nx)]

    # Mark cells within the corridor by walking each route and stamping a disc.
    selected: set[tuple[int, int]] = set()
    reach = CORRIDOR_MI + spacing_mi * 0.71
    for coords in routes:
        cum = cumulative_m(coords)
        step_m = spacing_mi * METERS_PER_MILE / 2
        for k in range(int(cum[-1] // step_m) + 2):
            lat, lon = point_at(coords, cum, k * step_m)
            ci = (lon - west) / dx_deg
            cj = (y1 - lat_to_merc_y(lat)) / dy_merc
            # local miles per cell vary with latitude in Mercator; use local scale
            cell_mi = dx_deg * MILES_PER_DEG_LAT * math.cos(math.radians(lat))
            r_cells = reach / cell_mi
            for j in range(max(0, int(cj - r_cells)), min(ny, int(cj + r_cells) + 2)):
                for i in range(max(0, int(ci - r_cells)), min(nx, int(ci + r_cells) + 2)):
                    if (i - ci) ** 2 + (j - cj) ** 2 <= r_cells**2:
                        selected.add((i, j))
    # Pixel (i, j) is centred on its grid point, so the image extends half a cell further.
    grid = {
        "nx": nx,
        "ny": ny,
        "bounds": [
            [merc_y_to_lat(y0 - dy_merc / 2), west - dx_deg / 2],
            [merc_y_to_lat(y1 + dy_merc / 2), east + dx_deg / 2],
        ],
    }
    cells = sorted(selected, key=lambda c: (c[1], c[0]))
    return grid, cells, row_lat, col_lon


def build_heatmap(routes: list[list[LatLon]], departure: datetime, load_lbs: float) -> dict:
    length_mi = sum(cumulative_m(r)[-1] for r in routes) / METERS_PER_MILE
    # area ≈ length × corridor width; choose spacing so the cell count stays under budget
    spacing = max(MIN_SPACING_MI, math.sqrt(length_mi * 2 * CORRIDOR_MI / MAX_CELLS))
    while True:
        grid, cells, row_lat, col_lon = _corridor_cells(routes, spacing)
        if len(cells) <= MAX_CELLS:
            break
        spacing *= 1.1

    start = floor_hour(departure)
    points = [(row_lat[j], col_lon[i]) for i, j in cells]
    series = fetch_series(points, start, start + timedelta(hours=HOURS))
    hours = [(start + timedelta(hours=h)).isoformat() for h in range(HOURS + 1)]

    out_cells = []
    for (i, j), p in zip(cells, points):
        s = series.get(snap(p))
        risk, wind, rain, snow = [], [], [], []
        for h in range(HOURS + 1):
            r = s.at(start + timedelta(hours=h)) if s else None
            if r is None:
                risk.append(None); wind.append(None); rain.append(None); snow.append(None)
                continue
            risk.append(round(risk_score(r.wind_mph, r.rain_in_hr, r.snow_in_hr, load_lbs), 2))
            wind.append(round(r.wind_mph, 1))
            rain.append(round(r.rain_in_hr, 3))
            snow.append(round(r.snow_in_hr, 2))
        out_cells.append({"i": i, "j": j, "risk": risk, "wind": wind, "rain": rain, "snow": snow})

    return {"grid": grid, "spacing_mi": round(spacing, 1), "start": start.isoformat(),
            "hours": hours, "cells": out_cells}
