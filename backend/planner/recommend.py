"""Route summaries and the recommendation ranking.

Ranking (from the brief), applied lexicographically:
  0. Fewest No Travel miles   (implicit: No Travel is worse than Severe)
  1. Fewest Severe miles
  2. Fewest High miles
  3. Lowest average risk      (mileage-weighted mean level, Low=0 … No Travel=4)
  4. Shortest travel time     (wall-clock, including required rest stops)

Miles are compared at 0.1 mi and average risk at 0.01 so float noise can't decide a tie.
"""

from __future__ import annotations

from dataclasses import dataclass

from .risk import Level, LEVEL_LABELS


@dataclass
class Summary:
    miles_by_level: dict[int, float]
    unknown_miles: float
    avg_risk: float | None
    max_level: int | None
    travel_s: float

    def key(self) -> tuple:
        m = self.miles_by_level
        return (
            round(m[Level.NO_TRAVEL], 1),
            round(m[Level.SEVERE], 1),
            round(m[Level.HIGH], 1),
            round(self.avg_risk if self.avg_risk is not None else 0.0, 2),
            round(self.travel_s),
        )

    def to_dict(self) -> dict:
        return {
            "miles_by_level": {LEVEL_LABELS[Level(k)]: round(v, 1) for k, v in self.miles_by_level.items()},
            "unknown_miles": round(self.unknown_miles, 1),
            "avg_risk": None if self.avg_risk is None else round(self.avg_risk, 3),
            "max_level": self.max_level,
        }


def summarize(checkpoints: list[dict], travel_s: float) -> Summary:
    """checkpoints: dicts with `level` (int or None) and `cover_mi`."""
    miles = {lvl: 0.0 for lvl in Level}
    unknown = 0.0
    weighted = 0.0
    for cp in checkpoints:
        if cp["level"] is None:
            unknown += cp["cover_mi"]
            continue
        miles[Level(cp["level"])] += cp["cover_mi"]
        weighted += cp["level"] * cp["cover_mi"]
    known = sum(miles.values())
    levels = [cp["level"] for cp in checkpoints if cp["level"] is not None]
    return Summary(
        miles_by_level=miles,
        unknown_miles=unknown,
        avg_risk=(weighted / known) if known else None,
        max_level=max(levels) if levels else None,
        travel_s=travel_s,
    )


CRITERIA = (  # (name when tied, comparative phrase when it decides)
    ("No Travel miles", "Fewer No Travel miles"),
    ("Severe miles", "Fewer Severe miles"),
    ("High miles", "Fewer High-risk miles"),
    ("average risk", "Lower average risk"),
    ("travel time", "Shorter travel time"),
)


def _fmt_delta(index: int, a: float, b: float) -> str:
    if index == 4:
        mins = round((b - a) / 60)
        return f"{mins // 60} h {mins % 60:02d} min faster" if mins >= 60 else f"{mins} min faster"
    if index == 3:
        return f"{a:.2f} vs {b:.2f}"
    return f"{a:.0f} vs {b:.0f} mi"


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def recommend(summaries: dict[str, Summary], names: dict[str, str]) -> dict:
    """Ranks route ids; explains the win against the runner-up by the deciding criterion."""
    ranking = sorted(summaries, key=lambda rid: summaries[rid].key())
    best = ranking[0]
    reason = "Only route available."
    if len(ranking) > 1:
        runner = ranking[1]
        ka, kb = summaries[best].key(), summaries[runner].key()
        for i, (a, b) in enumerate(zip(ka, kb)):
            if a != b:
                _, phrase = CRITERIA[i]
                earlier = [CRITERIA[j][0] for j in range(i)]
                reason = f"{phrase} than {names[runner]} ({_fmt_delta(i, a, b)})."
                if earlier:
                    reason += f" Tied on {_join(earlier)}."
                break
        else:
            reason = f"Identical risk and travel time to {names[runner]}."
    top = summaries[best]
    warning = None
    if top.miles_by_level[Level.NO_TRAVEL] > 0:
        warning = "Every route crosses No Travel conditions — consider delaying departure."
    elif top.miles_by_level[Level.SEVERE] > 0:
        warning = "Even the best route has Severe conditions — drive with caution or delay."
    if top.unknown_miles > 0:
        note = "Part of the trip is beyond the forecast horizon and was not scored."
        warning = f"{warning} {note}" if warning else note
    return {"route_id": best, "ranking": ranking, "reason": reason, "warning": warning}
