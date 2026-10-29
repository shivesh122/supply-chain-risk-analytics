import unittest

import numpy as np

from analytics.forecasting import holt_winters_fit, holt_winters_forecast, wape
from analytics.inventory_risk import risk_tier, stockout_probability
from analytics.suppliers import composite_score, tier


class RiskTests(unittest.TestCase):
    def test_probability_decreases_with_more_stock(self):
        low = stockout_probability(50, mu=10, sigma=3, lt_mean=7, lt_sd=1)
        high = stockout_probability(150, mu=10, sigma=3, lt_mean=7, lt_sd=1)
        self.assertGreater(low, 0.5)
        self.assertLess(high, 0.01)

    def test_probability_increases_with_lead_time_variability(self):
        steady = stockout_probability(90, mu=10, sigma=3, lt_mean=7, lt_sd=0.5)
        erratic = stockout_probability(90, mu=10, sigma=3, lt_mean=7, lt_sd=4)
        self.assertGreater(erratic, steady)

    def test_tiers(self):
        self.assertEqual(risk_tier(60, 30, 10), "High")
        self.assertEqual(risk_tier(5, 3, 10), "High")
        self.assertEqual(risk_tier(25, 30, 10), "Medium")
        self.assertEqual(risk_tier(5, 30, 10), "Low")


class SupplierTests(unittest.TestCase):
    def test_perfect_supplier_scores_100(self):
        self.assertAlmostEqual(float(composite_score(100, 100, 0, 0)), 100.0)

    def test_tiers(self):
        self.assertEqual(tier(90), "Preferred")
        self.assertEqual(tier(75), "Watch")
        self.assertEqual(tier(50), "At Risk")


class ForecastTests(unittest.TestCase):
    def test_recovers_weekly_pattern(self):
        pattern = np.array([10, 12, 11, 13, 15, 25, 22], dtype=float)
        y = np.tile(pattern, 20)
        level, trend, season, _ = holt_winters_fit(y, 0.2, 0.0, 0.2)
        fc = holt_winters_forecast(level, trend, season, len(y), 7)
        self.assertLess(wape(pattern, fc), 0.02)

    def test_wape(self):
        self.assertAlmostEqual(wape(np.array([10, 10]), np.array([8, 12])), 0.2)


if __name__ == "__main__":
    unittest.main()
