"""Weather risk classification — the assessment's risk table and load rules.

Bands are lower-inclusive: a value exactly on a boundary belongs to the higher band
(e.g. 25 mph wind is Moderate, 0.25 in/hr rain is High). The top of the Severe band
for rain/snow is inclusive (1.00 in/hr rain is Severe; No Travel is strictly ">1.00").
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Level(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return LEVEL_LABELS[self]


LEVEL_LABELS = {
    Level.LOW: "Low",
    Level.MODERATE: "Moderate",
    Level.HIGH: "High",
    Level.SEVERE: "Severe",
    Level.NO_TRAVEL: "No Travel",
}

# Lower bounds of Moderate, High, Severe for each condition.
WIND_BANDS_MPH = (25.0, 35.0, 45.0)
WIND_NO_TRAVEL_MPH = 55.0
RAIN_BANDS_IN_HR = (0.10, 0.25, 0.50)
RAIN_NO_TRAVEL_ABOVE = 1.00
SNOW_BANDS_IN_HR = (0.5, 1.0, 2.0)
SNOW_NO_TRAVEL_ABOVE = 3.0

# Load rules
HEAVY_LOAD_NO_TRAVEL_LBS = 30_000  # 45–54 mph with load > this -> No Travel
HEAVY_LOAD_SEVERE_LBS = 40_000  # 35–44 mph with load > this -> Severe


def _band(value: float, bands: tuple[float, float, float]) -> Level:
    level = Level.LOW
    for i, lower in enumerate(bands, start=1):
        if value >= lower:
            level = Level(i)
    return level


def classify_wind(mph: float, load_lbs: float) -> Level:
    if mph >= WIND_NO_TRAVEL_MPH:
        return Level.NO_TRAVEL
    level = _band(mph, WIND_BANDS_MPH)
    if level == Level.SEVERE and load_lbs > HEAVY_LOAD_NO_TRAVEL_LBS:
        return Level.NO_TRAVEL
    if level == Level.HIGH and load_lbs > HEAVY_LOAD_SEVERE_LBS:
        return Level.SEVERE
    return level


def classify_rain(in_hr: float) -> Level:
    if in_hr > RAIN_NO_TRAVEL_ABOVE:
        return Level.NO_TRAVEL
    return _band(in_hr, RAIN_BANDS_IN_HR)


def classify_snow(in_hr: float) -> Level:
    if in_hr > SNOW_NO_TRAVEL_ABOVE:
        return Level.NO_TRAVEL
    return _band(in_hr, SNOW_BANDS_IN_HR)


@dataclass(frozen=True)
class Assessment:
    level: Level
    wind: Level
    rain: Level
    snow: Level

    @property
    def factor(self) -> str | None:
        """The condition driving the overall level (None when everything is Low)."""
        if self.level == Level.LOW:
            return None
        for name in ("wind", "snow", "rain"):
            if getattr(self, name) == self.level:
                return name
        return None


def assess(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lbs: float) -> Assessment:
    """Overall level is the worst of the three conditions."""
    wind = classify_wind(wind_mph, load_lbs)
    rain = classify_rain(rain_in_hr)
    snow = classify_snow(snow_in_hr)
    return Assessment(level=max(wind, rain, snow), wind=wind, rain=rain, snow=snow)


# --- Continuous score (heatmap only) -----------------------------------------------------
# A 0–4 float whose integer part always equals the discrete level, so the heatmap's colors
# agree exactly with checkpoint levels while still blending smoothly inside a band.

def _continuous(value: float, edges: tuple[float, ...], level: Level) -> float:
    """edges = (0, moderate, high, severe, no_travel) lower bounds; interpolate within band."""
    if level == Level.NO_TRAVEL:
        return 4.0
    lo, hi = edges[level], edges[level + 1]
    frac = (value - lo) / (hi - lo) if hi > lo else 0.0
    return level + min(max(frac, 0.0), 0.999)


def risk_score(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lbs: float) -> float:
    a = assess(wind_mph, rain_in_hr, snow_in_hr, load_lbs)
    wind_edges = (0.0, *WIND_BANDS_MPH, WIND_NO_TRAVEL_MPH)
    if a.wind != _band(wind_mph, WIND_BANDS_MPH) and a.wind != Level.NO_TRAVEL:
        # Load rule bumped High -> Severe (35–44 mph, >40k lb): Severe band spans 35..45.
        wind_score = Level.SEVERE + min(max((wind_mph - 35.0) / 10.0, 0.0), 0.999)
    else:
        wind_score = _continuous(wind_mph, wind_edges, a.wind)
    rain_score = _continuous(rain_in_hr, (0.0, *RAIN_BANDS_IN_HR, RAIN_NO_TRAVEL_ABOVE), a.rain)
    snow_score = _continuous(snow_in_hr, (0.0, *SNOW_BANDS_IN_HR, SNOW_NO_TRAVEL_ABOVE), a.snow)
    return max(wind_score, rain_score, snow_score)
