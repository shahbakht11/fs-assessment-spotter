"""Hourly forecasts from Open-Meteo (no API key; batches many locations per request).

Units requested: wind in mph, precipitation and snowfall in inches. Open-Meteo labels each
hourly precipitation value with the *end* of the hour it accumulated over, while wind is an
instantaneous value at the timestamp. `Series.at()` therefore reads wind at the nearest hour
and rain/snow from the hour that contains the requested time.
"""

from __future__ import annotations

import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests
from django.conf import settings
from django.core.cache import cache

from .geo import LatLon

log = logging.getLogger(__name__)

HOURLY_VARS = ("wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall", "temperature_2m", "weather_code")
BATCH_SIZE = 100
SNAP_DEG = 0.02  # ~1.4 mi; well below the ~3 km model grid, lets nearby points share a fetch
FORECAST_HORIZON = timedelta(days=15)


class WeatherError(Exception):
    pass


@dataclass(frozen=True)
class Reading:
    wind_mph: float
    gust_mph: float
    rain_in_hr: float
    snow_in_hr: float
    temp_f: float
    code: int


@dataclass
class Series:
    start: datetime  # UTC, on the hour; index i is start + i hours
    wind: list[float]
    gust: list[float]
    rain: list[float]
    snow: list[float]
    temp: list[float]
    code: list[int]

    def __len__(self) -> int:
        return len(self.wind)

    def at(self, when: datetime) -> Reading | None:
        hours = (when - self.start).total_seconds() / 3600
        inst = round(hours)  # instantaneous fields: nearest hour
        accum = math.ceil(hours) if hours > 0 else 0  # hour-ending accumulation containing `when`
        if not (0 <= inst < len(self) and 0 <= accum < len(self)):
            return None
        vals = (self.wind[inst], self.gust[inst], self.rain[accum], self.snow[accum], self.temp[inst])
        if any(v is None for v in vals):
            return None
        return Reading(*vals, int(self.code[inst] or 0))


def snap(p: LatLon) -> LatLon:
    return (round(round(p[0] / SNAP_DEG) * SNAP_DEG, 4), round(round(p[1] / SNAP_DEG) * SNAP_DEG, 4))


def floor_hour(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def forecast_end_limit() -> datetime:
    return floor_hour(datetime.now(timezone.utc) + FORECAST_HORIZON)


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M")


def _cache_key(p: LatLon, start: datetime, end: datetime) -> str:
    return f"om:{p[0]}:{p[1]}:{_fmt(start)}:{_fmt(end)}"


def _parse(block: dict, start: datetime) -> Series:
    h = block["hourly"]
    rain = [(r or 0.0) + (s or 0.0) if r is not None else None for r, s in zip(h["rain"], h["showers"])]
    return Series(start, h["wind_speed_10m"], h["wind_gusts_10m"], rain, h["snowfall"],
                  h["temperature_2m"], h["weather_code"])


def _fetch_batch(session: requests.Session, pts: list[LatLon], start: datetime, end: datetime) -> list[Series]:
    params = {
        "latitude": ",".join(f"{p[0]:.4f}" for p in pts),
        "longitude": ",".join(f"{p[1]:.4f}" for p in pts),
        "hourly": ",".join(HOURLY_VARS),
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "temperature_unit": "fahrenheit",
        "timezone": "GMT",
        "start_hour": _fmt(start),
        "end_hour": _fmt(end),
    }
    for attempt in range(3):
        resp = session.get(settings.OPEN_METEO_URL, params=params, timeout=settings.HTTP_TIMEOUT_S)
        if resp.status_code == 429 and attempt < 2:
            time.sleep(1.5 * (attempt + 1))
            continue
        if resp.status_code != 200:
            raise WeatherError(f"Open-Meteo HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        blocks = data if isinstance(data, list) else [data]
        return [_parse(b, start) for b in blocks]
    raise WeatherError("Open-Meteo rate limit reached; try again in a minute.")


def fetch_series(points: list[LatLon], start: datetime, end: datetime) -> dict[LatLon, Series]:
    """Hourly series covering [start, end] for each point, keyed by the *snapped* point."""
    start, end = floor_hour(start), floor_hour(end) + timedelta(hours=1)
    end = min(end, forecast_end_limit())
    if end < start:
        return {}
    unique = list(dict.fromkeys(snap(p) for p in points))
    result: dict[LatLon, Series] = {}
    missing = []
    for p in unique:
        hit = cache.get(_cache_key(p, start, end))
        if hit is not None:
            result[p] = hit
        else:
            missing.append(p)
    if missing:
        session = requests.Session()
        session.headers["User-Agent"] = settings.HTTP_USER_AGENT
        batches = [missing[i:i + BATCH_SIZE] for i in range(0, len(missing), BATCH_SIZE)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            for batch, series in zip(batches, pool.map(lambda b: _fetch_batch(session, b, start, end), batches)):
                for p, s in zip(batch, series):
                    result[p] = s
                    cache.set(_cache_key(p, start, end), s, settings.WEATHER_CACHE_S)
    return result
