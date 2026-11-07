"""API + routing helpers, with all third-party services mocked."""

import json
from datetime import datetime, timedelta, timezone
from unittest import mock

from django.test import SimpleTestCase

from planner.geo import cumulative_m, decode_polyline
from planner.routing import Route, select_distinct, stitch
from planner.weather import Series, floor_hour, snap


def straight_route(start, end, n=60, hours=10.0, source="test"):
    coords = [(start[0] + (end[0] - start[0]) * i / (n - 1), start[1] + (end[1] - start[1]) * i / (n - 1))
              for i in range(n)]
    drive = [hours * 3600 * i / (n - 1) for i in range(n)]
    return Route(coords, cumulative_m(coords), drive, ["I 80"], source)


ORIGIN, DEST = (41.0, -90.0), (41.0, -100.0)  # ~520 mi due west


def fake_series(points, start, end, snap_deg=0.02, *, wind=10.0, rain=0.0, snow=0.0):
    start = floor_hour(start)
    n = int((floor_hour(end) - start).total_seconds() // 3600) + 2
    return {snap(p, snap_deg): Series(start, [wind] * n, [wind] * n, [rain] * n, [snow] * n, [40.0] * n, [0] * n)
            for p in points}


class RoutingHelperTests(SimpleTestCase):
    def test_decode_polyline6(self):
        # Two points encoded with precision 6 (Valhalla format)
        self.assertEqual(decode_polyline("_izlhA~rlgdF_{geC~ywl@", 6), [(38.5, -120.2), (40.7, -120.95)])

    def test_select_distinct_rejects_near_duplicates_and_long_detours(self):
        a = straight_route(ORIGIN, DEST)
        dup = straight_route(ORIGIN, DEST, n=90, hours=10.2)
        north = straight_route(ORIGIN, (41.0, -100.0), hours=11)
        north.coords = [(lat + 0.8 * (1 - abs(2 * i / 59 - 1)), lon) for i, (lat, lon) in enumerate(north.coords)]
        north.cum_m = cumulative_m(north.coords)
        too_slow = straight_route((40.0, -90.0), (40.0, -100.0), hours=17)
        chosen = select_distinct([a], [dup, too_slow, north])
        self.assertEqual(chosen, [a, north])

    def test_stitch_joins_legs_and_accumulates_time(self):
        leg1 = straight_route(ORIGIN, (41.0, -95.0), hours=5)
        leg2 = straight_route((41.0, -95.0), DEST, hours=4)
        joined = stitch([leg1, leg2])
        self.assertEqual(len(joined.coords), len(leg1.coords) + len(leg2.coords) - 1)
        self.assertAlmostEqual(joined.drive_s, 9 * 3600)


@mock.patch("planner.services.plan_routes")
@mock.patch("planner.services.fetch_series")
class PlanApiTests(SimpleTestCase):
    def post(self, **overrides):
        body = {
            "origin": {"lat": ORIGIN[0], "lon": ORIGIN[1]},
            "destination": {"lat": DEST[0], "lon": DEST[1]},
            "departure": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "load_lbs": 42_000,
            **overrides,
        }
        return self.client.post("/api/plan", json.dumps(body), content_type="application/json")

    def routes(self):
        fast = straight_route(ORIGIN, DEST, hours=9)
        slow = straight_route(ORIGIN, DEST, hours=12)
        return [fast, slow], "test", []

    def test_plan_returns_routes_checkpoints_and_recommendation(self, fetch, plan_routes):
        plan_routes.return_value = self.routes()
        fetch.side_effect = fake_series
        resp = self.post()
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual([r["id"] for r in data["routes"]], ["A", "B"])
        route = data["routes"][0]
        self.assertEqual(set(route["checkpoints"]), {"10", "25", "50"})
        cps = route["checkpoints"]["50"]
        self.assertEqual(cps[0]["mi"], 0)
        self.assertAlmostEqual(cps[-1]["mi"], route["distance_mi"], places=0)
        self.assertEqual(cps[0]["level"], 0)
        self.assertEqual(route["stops"][0]["kind"], "break")  # 9 h drive -> one 30 min break
        self.assertEqual(data["recommendation"]["10"]["route_id"], "A")

    def test_heavy_load_in_strong_wind_is_no_travel(self, fetch, plan_routes):
        plan_routes.return_value = self.routes()
        fetch.side_effect = lambda *a: fake_series(*a, wind=47)
        data = self.post(load_lbs=35_000).json()
        summary = data["routes"][0]["summary"]["25"]
        self.assertEqual(summary["max_level"], 4)
        self.assertGreater(summary["miles_by_level"]["No Travel"], 500)
        self.assertIn("No Travel", data["recommendation"]["25"]["warning"])

    def test_checkpoints_beyond_forecast_are_unknown(self, fetch, plan_routes):
        plan_routes.return_value = self.routes()
        fetch.return_value = {}
        cp = self.post().json()["routes"][0]["checkpoints"]["50"][0]
        self.assertIsNone(cp["level"])

    def test_validation_errors(self, fetch, plan_routes):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        far = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        for overrides, msg in [
            ({"origin": None}, "origin is required"),
            ({"load_lbs": -5}, "load_lbs"),
            ({"load_lbs": "heavy"}, "load_lbs"),
            ({"departure": past}, "past"),
            ({"departure": far}, "within 10 days"),
            ({"departure": "2026-11-07T10:00"}, "timezone"),
            ({"destination": {"lat": ORIGIN[0], "lon": ORIGIN[1]}}, "same place"),
        ]:
            with self.subTest(msg=msg):
                resp = self.post(**overrides)
                self.assertEqual(resp.status_code, 400)
                self.assertIn(msg, resp.json()["error"])
        plan_routes.assert_not_called()


@mock.patch("planner.heatmap.fetch_series")
class HeatmapApiTests(SimpleTestCase):
    def test_heatmap_grid_covers_corridor_for_49_hours(self, fetch):
        fetch.side_effect = lambda *a: fake_series(*a, wind=30)
        body = {
            "routes": [[list(ORIGIN), list(DEST)]],
            "departure": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "load_lbs": 20_000,
        }
        resp = self.client.post("/api/heatmap", json.dumps(body), content_type="application/json")
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(len(data["hours"]), 49)
        self.assertTrue(0 < len(data["cells"]) <= 320)
        cell = data["cells"][0]
        self.assertEqual(len(cell["risk"]), 49)
        self.assertTrue(1 <= cell["risk"][0] < 2)  # 30 mph -> Moderate band
        g = data["grid"]
        self.assertTrue(all(0 <= c["i"] < g["nx"] and 0 <= c["j"] < g["ny"] for c in data["cells"]))

    def test_rejects_bad_routes(self, fetch):
        resp = self.client.post("/api/heatmap", json.dumps({"routes": []}), content_type="application/json")
        self.assertEqual(resp.status_code, 400)


class WeatherBudgetTests(SimpleTestCase):
    def test_long_trips_share_forecast_cells_to_stay_within_budget(self):
        from planner.weather import choose_snap
        # ~2,800 mi of checkpoints every 10 mi across 3 routes ≈ 850 points
        pts = [(35 + 0.02 * k % 6, -118 + 0.05 * k) for k in range(850)]
        deg = choose_snap(pts, 350)
        self.assertLessEqual(len({snap(p, deg) for p in pts}), 350)
        self.assertEqual(choose_snap(pts[:100], 350), 0.02)  # short trips keep the fine grid

    def test_rate_limit_gives_a_clear_message(self):
        from planner.weather import WeatherError, _fetch_batch
        session = mock.Mock()
        session.get.return_value = mock.Mock(status_code=429, text='{"reason":"Minutely API request limit exceeded"}')
        start = datetime(2026, 11, 7, tzinfo=timezone.utc)
        with self.assertRaisesRegex(WeatherError, "600 forecast locations per minute"):
            _fetch_batch(session, [(41.0, -90.0)], start, start + timedelta(hours=3))
        self.assertEqual(session.get.call_count, 1)  # no pointless retry on the per-minute limit

    @mock.patch("planner.services.plan_routes")
    @mock.patch("planner.services.fetch_series")
    def test_rate_limit_returns_readable_error(self, fetch, plan_routes):
        from planner.weather import RATE_LIMIT_MESSAGE, WeatherError
        plan_routes.return_value = ([straight_route(ORIGIN, DEST)], "test", [])
        fetch.side_effect = WeatherError(RATE_LIMIT_MESSAGE)
        body = {"origin": {"lat": ORIGIN[0], "lon": ORIGIN[1]}, "destination": {"lat": DEST[0], "lon": DEST[1]},
                "departure": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), "load_lbs": 1000}
        resp = self.client.post("/api/plan", json.dumps(body), content_type="application/json")
        self.assertEqual(resp.status_code, 502)
        self.assertEqual(resp.json()["error"], RATE_LIMIT_MESSAGE)
