"""Timeline (ETA + hours of service), checkpoint sampling, and forecast-hour alignment."""

from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from planner.services import checkpoint_marks
from planner.timeline import HOUR, Timeline, hos_stops
from planner.weather import Series

T0 = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)


class HoursOfServiceTests(SimpleTestCase):
    def kinds(self, hours):
        return [(s.kind, s.at_drive_s / HOUR) for s in hos_stops(hours * HOUR)]

    def test_short_trip_has_no_stops(self):
        self.assertEqual(self.kinds(7.9), [])

    def test_break_after_8_hours(self):
        self.assertEqual(self.kinds(9), [("break", 8)])

    def test_no_rest_needed_when_arriving_at_exactly_11_hours(self):
        self.assertEqual(self.kinds(11), [("break", 8)])

    def test_multi_day_cycle(self):
        self.assertEqual(self.kinds(25), [("break", 8), ("rest", 11), ("break", 19), ("rest", 22)])


class TimelineTests(SimpleTestCase):
    def setUp(self):
        # 1,000 km at a steady 100 km/h -> 10 h of driving
        self.cum_m = [0.0, 500_000.0, 1_000_000.0]
        self.drive = [0.0, 5 * HOUR, 10 * HOUR]

    def test_eta_interpolates_drive_time(self):
        tl = Timeline(self.cum_m, self.drive, T0, include_hos=False)
        self.assertEqual(tl.eta(250_000), T0 + timedelta(hours=2.5))

    def test_eta_after_break_includes_the_break(self):
        tl = Timeline(self.cum_m, self.drive, T0)
        self.assertEqual(tl.eta(700_000), T0 + timedelta(hours=7))  # before the 8 h break
        self.assertEqual(tl.eta(900_000), T0 + timedelta(hours=9.5))  # after it
        self.assertEqual(tl.arrival, T0 + timedelta(hours=10.5))

    def test_stop_events_are_located_on_the_route(self):
        tl = Timeline(self.cum_m, self.drive, T0)
        (stop,) = tl.stop_events()
        self.assertEqual(stop["kind"], "break")
        self.assertAlmostEqual(stop["dist_m"], 800_000)
        self.assertEqual(stop["start"], T0 + timedelta(hours=8))


class CheckpointMarkTests(SimpleTestCase):
    def test_marks_include_origin_and_destination(self):
        marks = [m for m, _ in checkpoint_marks(52.0, 25)]
        self.assertEqual(marks, [0, 25, 50, 52.0])

    def test_coverage_sums_to_route_length(self):
        for total in (3.0, 52.0, 1015.3):
            for interval in (10, 25, 50):
                cover = sum(c for _, c in checkpoint_marks(total, interval))
                self.assertAlmostEqual(cover, total, places=6)

    def test_each_mark_covers_half_way_to_neighbours(self):
        self.assertEqual(checkpoint_marks(30.0, 10), [(0, 5.0), (10, 10.0), (20, 10.0), (30, 5.0)])


class ForecastAlignmentTests(SimpleTestCase):
    def setUp(self):
        n = 4
        self.series = Series(
            start=T0,
            wind=[10.0, 20.0, 30.0, 40.0],
            gust=[0.0] * n,
            rain=[0.0, 0.1, 0.2, 0.3],  # value at index i = rain during hour (i-1 .. i)
            snow=[0.0] * n,
            temp=[40.0] * n,
            code=[0] * n,
        )

    def test_wind_uses_nearest_hour_and_rain_uses_the_containing_hour(self):
        r = self.series.at(T0 + timedelta(minutes=80))  # 13:20
        self.assertEqual(r.wind_mph, 20.0)  # nearest is 13:00
        self.assertEqual(r.rain_in_hr, 0.2)  # 13:00–14:00 accumulation is labelled 14:00

    def test_outside_window_is_unknown(self):
        self.assertIsNone(self.series.at(T0 + timedelta(hours=10)))
