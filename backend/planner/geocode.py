"""Place search via Photon (OSM, autocomplete-friendly), with Nominatim as fallback."""

from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.core.cache import cache

log = logging.getLogger(__name__)


class GeocodeError(Exception):
    pass


def _label(props: dict) -> str:
    parts = [props.get("name"), props.get("city"), props.get("state"), props.get("countrycode")]
    seen: list[str] = []
    for p in parts:
        if p and p not in seen:
            seen.append(p)
    return ", ".join(seen)


PLACE_TYPES = {"city", "town", "village", "hamlet", "county", "state", "suburb", "locality"}


def _photon(q: str, limit: int) -> list[dict]:
    resp = requests.get(
        settings.PHOTON_URL,
        params={"q": q, "limit": limit + 4, "lang": "en"},
        headers={"User-Agent": settings.HTTP_USER_AGENT},
        timeout=settings.HTTP_TIMEOUT_S,
    )
    resp.raise_for_status()
    features = resp.json().get("features", [])
    # Photon ranks famous POIs ("New York City Ballet") above the city itself; for a trip
    # planner settlements are the likelier intent, so float them up (stable sort).
    features.sort(key=lambda f: f["properties"].get("osm_key") != "place"
                  or f["properties"].get("osm_value") not in PLACE_TYPES)
    out = []
    for f in features[:limit]:
        lon, lat = f["geometry"]["coordinates"]
        out.append({"label": _label(f["properties"]), "lat": lat, "lon": lon})
    return out


def _nominatim(q: str, limit: int) -> list[dict]:
    resp = requests.get(
        settings.NOMINATIM_URL,
        params={"q": q, "format": "jsonv2", "limit": limit},
        headers={"User-Agent": settings.HTTP_USER_AGENT},
        timeout=settings.HTTP_TIMEOUT_S,
    )
    resp.raise_for_status()
    return [{"label": r["display_name"], "lat": float(r["lat"]), "lon": float(r["lon"])} for r in resp.json()]


def search(q: str, limit: int = 6) -> list[dict]:
    q = q.strip()
    key = f"geo:{limit}:{q.lower()}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    for fn in (_photon, _nominatim):
        try:
            results = fn(q, limit)
            cache.set(key, results, 24 * 3600)
            return results
        except (requests.RequestException, KeyError, ValueError) as exc:
            log.warning("geocoder %s failed: %s", fn.__name__, exc)
    raise GeocodeError("Geocoding service unavailable.")
