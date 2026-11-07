"""The assessment brief, requirement by requirement, as executable checks.

Each test class maps to a section of the brief so a reviewer can tick them off.
All third-party services are mocked; nothing here touches the network.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest import mock

from django.test import SimpleTestCase

from planner.geo import cumulative_m
from planner.recommend import recommend, summarize
from planner.risk import Level, assess
from planner.routing import OsrmProvider, Route, RoutingError, ValhallaProvider, plan_routes
from planner.services import INTERVALS_MI, plan_trip
from planner.weather import Series, floor_hour, snap

L, M, H, S, NT = Level.LOW, Level.MODERATE, Level.HIGH, Level.SEVERE, Level.NO_TRAVEL
DEPART = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(minute=20, second=0, microsecond=0)
ORIGIN, DEST = (41.0, -90.0), (41.0, -100.0)  # ~520 mi


def route_through(points, hours, source="test", n_per_leg=40):
    """A route following straight legs through `points`, driven evenly in `hours`."""
    coords = []
    for a, b in zip(points, points[1:]):
        for i in range(n_per_leg):
            t = i / n_per_leg
            coords.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
    coords.append(points[-1])
    cum = cumulative_m(coords)
    drive = [hours * 3600 * c / cum[-1] for c in cum]
    return Route(coords, cum, drive, ["I 80"], source)


def series_by(fn):
    """fetch_series replacement: fn(lat, lon, hour_index) -> (wind, rain, snow)."""
    def fetch(points, start, end, snap_deg=0.02):
        start = floor_hour(start)
        n = int((floor_hour(end) - start).total_seconds() // 3600) + 3
        out = {}
        for p in points:
            sp = snap(p, snap_deg)
            vals = [fn(sp[0], sp[1], h) for h in range(n)]
            out[sp] = Series(start, [v[0] for v in vals], [v[0] for v in vals], [v[1] for v in vals],
                             [v[2] for v in vals], [40.0] * n, [0] * n)
        return out
    return fetch


# ---------------------------------------------------------------------------------------------
# "Risk Rules — use these thresholds to classify weather at each checkpoint"
# ---------------------------------------------------------------------------------------------

class SpecRiskTable(SimpleTestCase):
    """Every cell of the brief's table, at both ends of each band (light load)."""

    TABLE = {
        "wind": [(0, L), (24.9, L), (25, M), (34, M), (35, H), (44, H), (45, S), (54, S), (55, NT), (70, NT)],
        "rain": [(0, L), (0.09, L), (0.10, M), (0.24, M), (0.25, H), (0.49, H), (0.50, S), (1.00, S), (1.01, NT)],
        "snow": [(0, L), (0.4, L), (0.5, M), (0.9, M), (1.0, H), (1.9, H), (2.0, S), (3.0, S), (3.1, NT)],
    }

    def test_table(self):
        for condition, rows in self.TABLE.items():
            for value, expected in rows:
                kwargs = {"wind_mph": 0, "rain_in_hr": 0, "snow_in_hr": 0, "load_lbs": 10_000}
                kwargs[{"wind": "wind_mph", "rain": "rain_in_hr", "snow": "snow_in_hr"}[condition]] = value
                with self.subTest(condition=condition, value=value):
                    self.assertEqual(assess(**kwargs).level, expected)

    def test_checkpoint_level_is_the_worst_condition(self):
        self.assertEqual(assess(30, 0.3, 2.5, 10_000).level, S)  # Moderate wind, High rain, Severe snow


class SpecLoadRules(SimpleTestCase):
    """'≥55 mph → No Travel for any load; 45–54 mph + >30,000 lb → No Travel;
    35–44 mph + >40,000 lb → Severe'."""

    def wind(self, mph, lbs):
        return assess(mph, 0, 0, lbs).level

    def test_55_mph_no_travel_for_any_load(self):
        for lbs in (0, 15_000, 30_000, 40_000, 80_000):
            self.assertEqual(self.wind(55, lbs), NT)

    def test_45_to_54_mph(self):
        self.assertEqual(self.wind(50, 30_000), S)  # not over 30,000
        self.assertEqual(self.wind(50, 30_001), NT)
        self.assertEqual(self.wind(45, 45_000), NT)

    def test_35_to_44_mph(self):
        self.assertEqual(self.wind(40, 40_000), H)  # not over 40,000
        self.assertEqual(self.wind(40, 40_001), S)
        self.assertEqual(self.wind(35, 79_000), S)

    def test_load_never_changes_rain_or_snow(self):
        self.assertEqual(assess(0, 0.3, 0, 80_000).level, assess(0, 0.3, 0, 0).level)
        self.assertEqual(assess(0, 0, 1.5, 80_000).level, assess(0, 0, 1.5, 0).level)


# ---------------------------------------------------------------------------------------------
# "Route Recommendation — prefer: 1. fewest Severe miles 2. fewest High miles
#  3. lowest average risk 4. shortest travel times"
# ---------------------------------------------------------------------------------------------

class SpecRecommendationOrder(SimpleTestCase):
    NAMES = {"A": "Route A", "B": "Route B"}

    def pick(self, a, b):
        def summary(segments, hours):
            return summarize([{"level": lvl, "cover_mi": mi} for lvl, mi in segments], hours * 3600)
        return recommend({"A": summary(*a), "B": summary(*b)}, self.NAMES)["route_id"]

    def test_1_severe_miles_outrank_everything_after(self):
        # B: more High miles, higher average and slower — still wins on Severe miles.
        self.assertEqual(self.pick(([(S, 10), (L, 90)], 5), ([(S, 5), (H, 80), (L, 15)], 9)), "B")

    def test_2_high_miles_when_severe_tied(self):
        self.assertEqual(self.pick(([(H, 30), (L, 70)], 5), ([(H, 10), (M, 90)], 9)), "B")

    def test_3_average_risk_when_severe_and_high_tied(self):
        self.assertEqual(self.pick(([(M, 60), (L, 40)], 5), ([(M, 20), (L, 80)], 9)), "B")

    def test_4_travel_time_when_all_risk_tied(self):
        self.assertEqual(self.pick(([(L, 100)], 9), ([(L, 100)], 5)), "B")


# ---------------------------------------------------------------------------------------------
# "Generate 3 route options using a routing API"
# ---------------------------------------------------------------------------------------------

def leg_router(a, b, alternates=0, heading_a=None, heading_b=None, exclude=None):
    """Valhalla stand-in for single legs: a straight route between the two points."""
    return [route_through([a, b], hours=2.5, source="valhalla-truck")]


class SpecThreeRoutes(SimpleTestCase):
    def test_three_distinct_routes_even_when_the_api_returns_one(self):
        main = route_through([ORIGIN, DEST], hours=9, source="valhalla-truck")
        north = route_through([ORIGIN, (42.2, -95.0), DEST], hours=10)
        south = route_through([ORIGIN, (39.8, -95.0), DEST], hours=10.5)

        def valhalla(a, b, alternates=0, **kw):
            return [main] if alternates else leg_router(a, b)

        with mock.patch.object(ValhallaProvider, "routes", side_effect=valhalla), \
                mock.patch.object(OsrmProvider, "routes", return_value=[main, north, south]):
            routes, provider, warnings = plan_routes(ORIGIN, DEST, 40_000)
        self.assertEqual(len(routes), 3)
        self.assertEqual(provider, "valhalla-truck")
        self.assertEqual(warnings, [])
        self.assertEqual([r.drive_s for r in routes], sorted(r.drive_s for r in routes))  # fastest first

    def test_falls_back_to_osrm_when_truck_routing_fails(self):
        routes3 = [route_through([ORIGIN, (41.0 + d, -95.0), DEST], hours=9 + abs(d)) for d in (0, 1.2, -1.2)]
        with mock.patch.object(ValhallaProvider, "routes", side_effect=RoutingError("too long")), \
                mock.patch.object(OsrmProvider, "routes", return_value=routes3):
            routes, provider, warnings = plan_routes(ORIGIN, DEST, 40_000)
        self.assertEqual((len(routes), provider), (3, "osrm"))
        self.assertIn("65 mph", warnings[0])

    def test_truck_router_gets_gross_weight(self):
        captured = {}

        def fake_init(self, session, gross_lbs):
            captured["gross"] = gross_lbs
            raise RoutingError("stop here")

        with mock.patch.object(ValhallaProvider, "__init__", fake_init), self.assertRaises(RoutingError):
            plan_routes(ORIGIN, DEST, 42_000)
        self.assertEqual(captured["gross"], 42_000 + 35_000)  # load + tractor-trailer tare


# ---------------------------------------------------------------------------------------------
# "Sample weather every 10 / 25 / 50 miles, using the truck's estimated arrival time"
# ---------------------------------------------------------------------------------------------

@mock.patch("planner.services.plan_routes")
class SpecSampling(SimpleTestCase):
    def plan(self, plan_routes, fetch, load=20_000, routes=None, hos=True):
        plan_routes.return_value = (routes or [route_through([ORIGIN, DEST], hours=9)], "test", [])
        with mock.patch("planner.services.fetch_series", side_effect=series_by(fetch)):
            return plan_trip(ORIGIN, DEST, DEPART, load, include_hos=hos)

    def test_checkpoints_every_10_25_50_miles(self, plan_routes):
        route = self.plan(plan_routes, lambda la, lo, h: (5, 0, 0))["routes"][0]
        for interval in INTERVALS_MI:
            miles = [cp["mi"] for cp in route["checkpoints"][str(interval)]]
            with self.subTest(interval=interval):
                self.assertEqual(miles[:-1], [k * interval for k in range(len(miles) - 1)])
                self.assertAlmostEqual(miles[-1], route["distance_mi"], places=0)  # destination too
                self.assertTrue(all(0 < b - a <= interval for a, b in zip(miles, miles[1:])))
                covered = sum(cp["cover_mi"] for cp in route["checkpoints"][str(interval)])
                self.assertAlmostEqual(covered, route["distance_mi"], delta=0.1)

    def test_weather_is_read_at_each_checkpoints_eta_not_departure(self, plan_routes):
        # Wind = 10 + hour index, so every checkpoint should see the wind of *its* hour.
        route = self.plan(plan_routes, lambda la, lo, h: (10.0 + h, 0, 0), hos=False)["routes"][0]
        start = floor_hour(DEPART)
        cps = route["checkpoints"]["25"]
        for cp in cps:
            eta = datetime.fromisoformat(cp["eta"])
            expected_hour = round((eta - start).total_seconds() / 3600)
            self.assertEqual(cp["wind"], 10.0 + expected_hour, cp)
        self.assertGreater(cps[-1]["wind"], cps[0]["wind"])  # conditions change along the trip

    def test_etas_increase_along_the_route_and_match_drive_time(self, plan_routes):
        route = self.plan(plan_routes, lambda la, lo, h: (5, 0, 0), hos=False)["routes"][0]
        etas = [datetime.fromisoformat(cp["eta"]) for cp in route["checkpoints"]["10"]]
        self.assertEqual(etas, sorted(etas))
        self.assertAlmostEqual((etas[-1] - DEPART).total_seconds() / 3600, 9, places=2)

    def test_load_weight_changes_the_risk_of_the_same_weather(self, plan_routes):
        windy = lambda la, lo, h: (40, 0, 0)  # noqa: E731  35–44 mph
        light = self.plan(plan_routes, windy, load=20_000)["routes"][0]["summary"]["25"]
        heavy = self.plan(plan_routes, windy, load=45_000)["routes"][0]["summary"]["25"]
        self.assertEqual((light["max_level"], heavy["max_level"]), (H, S))


# ---------------------------------------------------------------------------------------------
# "Recommend the best route, balancing weather risk and travel time" (end to end)
# ---------------------------------------------------------------------------------------------

@mock.patch("planner.services.plan_routes")
class SpecEndToEndRecommendation(SimpleTestCase):
    def test_slower_route_wins_when_the_fast_one_drives_through_a_storm(self, plan_routes):
        fast_stormy = route_through([ORIGIN, DEST], hours=8)  # lat 41
        slow_calm = route_through([ORIGIN, (43.0, -95.0), DEST], hours=11)  # bows north
        plan_routes.return_value = ([fast_stormy, slow_calm], "test", [])
        storm = series_by(lambda la, lo, h: (50 if la < 41.3 and -97 < lo < -93 else 8, 0, 0))
        with mock.patch("planner.services.fetch_series", side_effect=storm):
            data = plan_trip(ORIGIN, DEST, DEPART, 20_000)
        for interval in ("10", "25", "50"):
            rec = data["recommendation"][interval]
            with self.subTest(interval=interval):
                self.assertEqual(rec["route_id"], "B")
                self.assertIn("Severe", rec["reason"])
        a = data["routes"][0]["summary"]["10"]["miles_by_level"]
        self.assertGreater(a["Severe"], 100)

    def test_faster_route_wins_when_weather_is_equal(self, plan_routes):
        plan_routes.return_value = ([route_through([ORIGIN, DEST], hours=8),
                                     route_through([ORIGIN, (43.0, -95.0), DEST], hours=11)], "test", [])
        with mock.patch("planner.services.fetch_series", side_effect=series_by(lambda *a: (5, 0, 0))):
            data = plan_trip(ORIGIN, DEST, DEPART, 20_000)
        self.assertEqual(data["recommendation"]["25"]["route_id"], "A")
        self.assertIn("travel time", data["recommendation"]["25"]["reason"])


# ---------------------------------------------------------------------------------------------
# "Show a weather heatmap along the trip corridor with a 0–48 hour forecast slider"
# ---------------------------------------------------------------------------------------------

class SpecHeatmap(SimpleTestCase):
    def test_hours_0_to_48_from_departure_and_only_near_the_route(self):
        fetch = series_by(lambda la, lo, h: (10 + h, 0, 0))
        with mock.patch("planner.heatmap.fetch_series", side_effect=fetch):
            resp = self.client.post("/api/heatmap", json.dumps({
                "routes": [[list(ORIGIN), list(DEST)]],
                "departure": DEPART.isoformat(),
                "load_lbs": 20_000,
            }), content_type="application/json")
        data = resp.json()
        hours = [datetime.fromisoformat(h) for h in data["hours"]]
        self.assertEqual(len(hours), 49)
        self.assertEqual(hours[0], floor_hour(DEPART))
        self.assertEqual(hours[-1] - hours[0], timedelta(hours=48))
        # Cells are in the corridor: the straight route runs along lat 41, corridor is 45 mi.
        g = data["grid"]
        (south, _), (north, _) = g["bounds"]
        self.assertLess(north - south, 4)
        # Values change over time (the slider has something to show).
        cell = data["cells"][0]
        self.assertNotEqual(cell["wind"][0], cell["wind"][48])
