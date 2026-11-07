from django.test import SimpleTestCase

from planner.recommend import recommend, summarize

NAMES = {"A": "Route A", "B": "Route B", "C": "Route C"}


def cps(*segments):
    """segments: (level, miles) pairs -> checkpoint dicts."""
    return [{"level": lvl, "cover_mi": mi} for lvl, mi in segments]


def rec(**routes):
    summaries = {rid: summarize(c, travel_s) for rid, (c, travel_s) in routes.items()}
    return recommend(summaries, NAMES)


class RecommendationOrderTests(SimpleTestCase):
    def test_fewer_severe_miles_beats_faster_route(self):
        r = rec(A=(cps((3, 20), (0, 80)), 3600), B=(cps((2, 50), (0, 50)), 7200))
        self.assertEqual(r["route_id"], "B")
        self.assertIn("Fewer Severe miles", r["reason"])

    def test_no_travel_is_worse_than_any_amount_of_severe(self):
        r = rec(A=(cps((4, 1), (0, 99)), 3600), B=(cps((3, 90), (0, 10)), 3600))
        self.assertEqual(r["route_id"], "B")

    def test_tied_severe_then_fewer_high_miles(self):
        r = rec(A=(cps((3, 10), (2, 30), (0, 60)), 3600), B=(cps((3, 10), (2, 20), (0, 70)), 9000))
        self.assertEqual(r["route_id"], "B")
        self.assertIn("Tied on No Travel miles and Severe miles", r["reason"])

    def test_tied_severe_and_high_then_lower_average_risk(self):
        r = rec(A=(cps((1, 60), (0, 40)), 3600), B=(cps((1, 20), (0, 80)), 5400))
        self.assertEqual(r["route_id"], "B")
        self.assertIn("Lower average risk", r["reason"])

    def test_identical_risk_then_shortest_travel_time(self):
        r = rec(A=(cps((0, 100)), 9000), B=(cps((0, 120)), 7200), C=(cps((0, 90)), 8000))
        self.assertEqual(r["ranking"], ["B", "C", "A"])
        self.assertIn("13 min faster", r["reason"])

    def test_average_risk_is_mileage_weighted(self):
        s = summarize(cps((2, 10), (0, 30)), 0)
        self.assertAlmostEqual(s.avg_risk, 0.5)


class RecommendationWarningTests(SimpleTestCase):
    def test_warns_when_every_route_has_no_travel(self):
        r = rec(A=(cps((4, 5), (0, 95)), 3600), B=(cps((4, 10), (0, 90)), 3600))
        self.assertIn("No Travel", r["warning"])

    def test_unknown_miles_are_excluded_from_average_and_flagged(self):
        s = summarize([{"level": 2, "cover_mi": 10}, {"level": None, "cover_mi": 30}], 0)
        self.assertEqual(s.avg_risk, 2)
        self.assertEqual(s.unknown_miles, 30)
        r = recommend({"A": s}, NAMES)
        self.assertIn("forecast horizon", r["warning"])
