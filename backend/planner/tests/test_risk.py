import math

from django.test import SimpleTestCase

from planner.risk import Level, assess, classify_rain, classify_snow, classify_wind, risk_score

L, M, H, S, NT = Level.LOW, Level.MODERATE, Level.HIGH, Level.SEVERE, Level.NO_TRAVEL


class WindTableTests(SimpleTestCase):
    def test_bands_light_load(self):
        cases = [(0, L), (24.9, L), (25, M), (34.9, M), (35, H), (44.9, H), (45, S), (54.9, S), (55, NT), (80, NT)]
        for mph, expected in cases:
            with self.subTest(mph=mph):
                self.assertEqual(classify_wind(mph, 20_000), expected)


class LoadRuleTests(SimpleTestCase):
    def test_55_mph_is_no_travel_for_any_load(self):
        for load in (0, 10_000, 30_000, 80_000):
            self.assertEqual(classify_wind(55, load), NT)

    def test_45_54_mph_over_30k_is_no_travel(self):
        self.assertEqual(classify_wind(45, 30_000), S)  # rule is strictly "> 30,000 lb"
        self.assertEqual(classify_wind(45, 30_001), NT)
        self.assertEqual(classify_wind(54.9, 30_001), NT)

    def test_35_44_mph_over_40k_is_severe(self):
        self.assertEqual(classify_wind(35, 40_000), H)
        self.assertEqual(classify_wind(35, 40_001), S)
        self.assertEqual(classify_wind(44.9, 45_000), S)

    def test_35_44_mph_between_30k_and_40k_stays_high(self):
        self.assertEqual(classify_wind(40, 35_000), H)

    def test_load_rules_do_not_touch_lower_winds(self):
        self.assertEqual(classify_wind(30, 80_000), M)


class PrecipTableTests(SimpleTestCase):
    def test_rain_bands(self):
        cases = [(0, L), (0.099, L), (0.10, M), (0.249, M), (0.25, H), (0.499, H), (0.50, S), (1.00, S), (1.01, NT)]
        for v, expected in cases:
            with self.subTest(rain=v):
                self.assertEqual(classify_rain(v), expected)

    def test_snow_bands(self):
        cases = [(0, L), (0.49, L), (0.5, M), (0.99, M), (1.0, H), (1.99, H), (2.0, S), (3.0, S), (3.01, NT)]
        for v, expected in cases:
            with self.subTest(snow=v):
                self.assertEqual(classify_snow(v), expected)


class AssessTests(SimpleTestCase):
    def test_overall_is_worst_condition_and_names_the_factor(self):
        a = assess(wind_mph=30, rain_in_hr=0.3, snow_in_hr=0, load_lbs=10_000)
        self.assertEqual(a.level, H)
        self.assertEqual(a.factor, "rain")

    def test_calm_weather_has_no_factor(self):
        self.assertIsNone(assess(5, 0, 0, 40_000).factor)

    def test_heavy_load_wind_beats_moderate_snow(self):
        a = assess(wind_mph=40, rain_in_hr=0, snow_in_hr=0.6, load_lbs=42_000)
        self.assertEqual((a.level, a.factor), (S, "wind"))


class RiskScoreTests(SimpleTestCase):
    def test_integer_part_always_matches_discrete_level(self):
        for wind in range(0, 70, 3):
            for rain in (0, 0.05, 0.1, 0.3, 0.7, 1.0, 1.2):
                for snow in (0, 0.7, 1.5, 2.5, 3.5):
                    for load in (10_000, 35_000, 45_000):
                        level = assess(wind, rain, snow, load).level
                        score = risk_score(wind, rain, snow, load)
                        self.assertEqual(math.floor(score), int(level), (wind, rain, snow, load, score))

    def test_score_increases_within_a_band(self):
        self.assertLess(risk_score(26, 0, 0, 0), risk_score(33, 0, 0, 0))
