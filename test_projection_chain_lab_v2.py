import unittest

from services.projection_chain_lab_v2 import (
    Strategy,
    _adaptive_landing_fraction,
    _simulate_strategy,
)


class ProjectionChainLabV2Tests(unittest.TestCase):
    def setUp(self):
        self.cycles = [
            {"restock_time": 0, "depletion_time": 600, "lifetime_seconds": 600},
            {"restock_time": 7800, "depletion_time": 8400, "lifetime_seconds": 600},
            {"restock_time": 15600, "depletion_time": 16200, "lifetime_seconds": 600},
            {"restock_time": 23400, "depletion_time": 24000, "lifetime_seconds": 600},
            {"restock_time": 31200, "depletion_time": 31800, "lifetime_seconds": 600},
            {"restock_time": 39000, "depletion_time": 39600, "lifetime_seconds": 600},
            {"restock_time": 46800, "depletion_time": 47400, "lifetime_seconds": 600},
            {"restock_time": 54600, "depletion_time": 55200, "lifetime_seconds": 600},
            {"restock_time": 62400, "depletion_time": 63000, "lifetime_seconds": 600},
            {"restock_time": 70800, "depletion_time": 71400, "lifetime_seconds": 600},
            {"restock_time": 78600, "depletion_time": 79200, "lifetime_seconds": 600},
        ]
        self.waits = {
            600: 7200,
            8400: 7200,
            16200: 7200,
            24000: 7200,
            31800: 7200,
            39600: 7200,
            47400: 7200,
            55200: 7200,
            63000: 7800,
            71400: 7200,
        }

    def test_frozen_depth2_does_not_reanchor(self):
        rows = _simulate_strategy(
            self.cycles,
            self.waits,
            Strategy("all_median", "all_median", "midpoint"),
            travel_seconds=3600,
            max_depth=2,
            min_history=8,
        )

        anchor_rows = [r for r in rows if r["anchor_timestamp"] == 63000]
        p2 = next(r for r in anchor_rows if r["depth"] == 2)

        self.assertEqual(p2["predicted_restock_timestamp"], 78000)
        self.assertEqual(p2["actual_restock_timestamp"], 78600)
        self.assertEqual(p2["signed_error_seconds"], 600)

    def test_real_flight_reachability_is_recorded(self):
        rows = _simulate_strategy(
            self.cycles,
            self.waits,
            Strategy("all_median", "all_median", "midpoint"),
            travel_seconds=8000,
            max_depth=2,
            min_history=8,
        )

        anchor_rows = [r for r in rows if r["anchor_timestamp"] == 63000]
        p1 = next(r for r in anchor_rows if r["depth"] == 1)
        p2 = next(r for r in anchor_rows if r["depth"] == 2)

        self.assertEqual(p1["actionable_from_anchor"], 0)
        self.assertEqual(p2["actionable_from_anchor"], 1)



    def test_adaptive_fraction_learns_later_landing_when_forecast_is_early(self):
        prior = []
        for i in range(12):
            predicted = 10000 + i * 1000
            actual = predicted + 240
            prior.append({
                "predicted_restock_timestamp": predicted,
                "actual_restock_timestamp": actual,
                "actual_depletion_timestamp": actual + 600,
                "lifetime_estimate_seconds": 600,
                "window_end_timestamp": None,
            })

        fraction = _adaptive_landing_fraction(prior)
        self.assertIsNotNone(fraction)
        self.assertGreaterEqual(fraction, 0.70)


if __name__ == "__main__":
    unittest.main()
