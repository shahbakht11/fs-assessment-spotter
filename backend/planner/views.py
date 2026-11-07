"""JSON API. Input validation lives here; planning logic lives in services/heatmap."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from functools import wraps

import requests
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import geocode
from .heatmap import build_heatmap
from .routing import RoutingError
from .services import plan_trip
from .weather import WeatherError

log = logging.getLogger(__name__)

MAX_LOAD_LBS = 80_000
MAX_DEPARTURE_AHEAD = timedelta(days=10)
MAX_DEPARTURE_BEHIND = timedelta(hours=1)
MAX_HEATMAP_ROUTES = 3
MAX_HEATMAP_POINTS = 2000


class BadRequest(Exception):
    pass


def api(view):
    """Uniform JSON errors: 400 for bad input, 502 for upstream API failures."""

    @wraps(view)
    def wrapper(request: HttpRequest, *args, **kwargs):
        try:
            return JsonResponse(view(request, *args, **kwargs))
        except BadRequest as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except (RoutingError, WeatherError, geocode.GeocodeError, requests.RequestException) as exc:
            log.warning("upstream failure: %s", exc)
            return JsonResponse({"error": f"Upstream service error: {exc}"}, status=502)

    return wrapper


def _body(request: HttpRequest) -> dict:
    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError as exc:
        raise BadRequest("Body must be JSON.") from exc
    if not isinstance(data, dict):
        raise BadRequest("Body must be a JSON object.")
    return data


def _coord(value, field: str) -> tuple[float, float]:
    try:
        lat, lon = float(value[0]), float(value[1])
    except (TypeError, ValueError, IndexError, KeyError) as exc:
        raise BadRequest(f"{field} must be [lat, lon].") from exc
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise BadRequest(f"{field} is out of range.")
    return lat, lon


def _place(value, field: str) -> tuple[float, float]:
    """Accepts {"lat", "lon"} (from autocomplete) or free text to geocode."""
    if isinstance(value, dict) and "lat" in value and "lon" in value:
        return _coord((value["lat"], value["lon"]), field)
    if isinstance(value, str) and value.strip():
        hits = geocode.search(value, limit=1)
        if not hits:
            raise BadRequest(f"Could not find {field} “{value}”.")
        return hits[0]["lat"], hits[0]["lon"]
    raise BadRequest(f"{field} is required.")


def _departure(value) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise BadRequest("departure must be an ISO-8601 datetime.") from exc
    if dt.tzinfo is None:
        raise BadRequest("departure must include a timezone offset.")
    dt = dt.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if dt < now - MAX_DEPARTURE_BEHIND:
        raise BadRequest("departure is in the past.")
    if dt > now + MAX_DEPARTURE_AHEAD:
        raise BadRequest("departure must be within 10 days (weather forecast horizon).")
    return dt


def _load(value) -> float:
    try:
        load = float(value)
    except (TypeError, ValueError) as exc:
        raise BadRequest("load_lbs must be a number.") from exc
    if not 0 <= load <= MAX_LOAD_LBS:
        raise BadRequest(f"load_lbs must be between 0 and {MAX_LOAD_LBS:,}.")
    return load


@require_GET
def health(request):
    return JsonResponse({"ok": True})


@require_GET
@api
def geocode_view(request):
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return {"results": []}
    return {"results": geocode.search(q[:120])}


@csrf_exempt
@require_POST
@api
def plan_view(request):
    data = _body(request)
    origin = _place(data.get("origin"), "origin")
    dest = _place(data.get("destination"), "destination")
    if origin == dest:
        raise BadRequest("Origin and destination are the same place.")
    return plan_trip(
        origin,
        dest,
        _departure(data.get("departure")),
        _load(data.get("load_lbs")),
        include_hos=bool(data.get("include_hos", True)),
    )


@csrf_exempt
@require_POST
@api
def heatmap_view(request):
    data = _body(request)
    raw_routes = data.get("routes")
    if not isinstance(raw_routes, list) or not 1 <= len(raw_routes) <= MAX_HEATMAP_ROUTES:
        raise BadRequest("routes must be a list of 1–3 polylines.")
    routes = []
    for r in raw_routes:
        if not isinstance(r, list) or len(r) < 2 or len(r) > MAX_HEATMAP_POINTS:
            raise BadRequest(f"each route needs 2–{MAX_HEATMAP_POINTS} points.")
        routes.append([_coord(p, "route point") for p in r])
    return build_heatmap(routes, _departure(data.get("departure")), _load(data.get("load_lbs")))
