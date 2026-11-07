"""Wall-clock timeline for a truck along a route, including FMCSA hours-of-service stops.

The routing API gives *driving* time per vertex. A property-carrying driver must take a
30-minute break after 8 hours of driving and a 10-hour rest after 11 hours of driving, so
on a multi-day trip the arrival time at a checkpoint is driving time plus the stops taken
before it. (The 14-hour on-duty window is not modelled: driving is assumed continuous.)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .geo import interpolate

HOUR = 3600.0
BREAK_AFTER_DRIVE_S = 8 * HOUR
BREAK_S = 0.5 * HOUR
REST_AFTER_DRIVE_S = 11 * HOUR
REST_S = 10 * HOUR


@dataclass(frozen=True)
class Stop:
    kind: str  # "break" | "rest"
    at_drive_s: float
    duration_s: float


def hos_stops(total_drive_s: float) -> list[Stop]:
    """Stops strictly before the end of the drive (none needed on arrival)."""
    stops: list[Stop] = []
    shift_start = 0.0
    while True:
        brk = shift_start + BREAK_AFTER_DRIVE_S
        rest = shift_start + REST_AFTER_DRIVE_S
        if brk >= total_drive_s:
            break
        stops.append(Stop("break", brk, BREAK_S))
        if rest >= total_drive_s:
            break
        stops.append(Stop("rest", rest, REST_S))
        shift_start = rest
    return stops


class Timeline:
    """Maps distance along the route (meters) to drive time and to wall-clock ETA."""

    def __init__(self, cum_m: list[float], cum_drive_s: list[float], departure: datetime,
                 include_hos: bool = True):
        self.cum_m = cum_m
        self.cum_drive_s = cum_drive_s
        self.departure = departure
        self.total_drive_s = cum_drive_s[-1]
        self.stops = hos_stops(self.total_drive_s) if include_hos else []

    def drive_s_at(self, dist_m: float) -> float:
        return interpolate(self.cum_m, self.cum_drive_s, dist_m)

    def dist_m_at_drive_s(self, drive_s: float) -> float:
        return interpolate(self.cum_drive_s, self.cum_m, drive_s)

    def elapsed_s(self, drive_s: float) -> float:
        return drive_s + sum(s.duration_s for s in self.stops if s.at_drive_s < drive_s)

    def eta(self, dist_m: float) -> datetime:
        return self.departure + timedelta(seconds=self.elapsed_s(self.drive_s_at(dist_m)))

    @property
    def total_elapsed_s(self) -> float:
        return self.elapsed_s(self.total_drive_s)

    @property
    def arrival(self) -> datetime:
        return self.departure + timedelta(seconds=self.total_elapsed_s)

    def stop_events(self) -> list[dict]:
        """Stops with their position and wall-clock start, for display."""
        out = []
        for s in self.stops:
            start = self.departure + timedelta(seconds=self.elapsed_s(s.at_drive_s))
            out.append({
                "kind": s.kind,
                "dist_m": self.dist_m_at_drive_s(s.at_drive_s),
                "start": start,
                "duration_s": s.duration_s,
            })
        return out
