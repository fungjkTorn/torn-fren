import unittest

from services.projection_engine_v6 import (
    ArrivalStateConfig,
    choose_arrival_offset,
    selective_summary,
)


class ProjectionEngineV6Tests(unittest.TestCase):
    def test_recent_interval_overlap_finds_common_live_window(self):
        prior = []
        for i, err in enumerate((90, 120, 150, 110, 130, 140, 100, 125)):
            prior.append({
                "anchor_timestamp": i,
                "actual_restock_timestamp": 10000 + i * 1000,
                "signed_error_seconds": float(err),
                "actual_lifetime_seconds": 360.0,
            })
        config = ArrivalStateConfig(
            residual_window=8,
            weighting="uniform",
            tod_hours=None,
            bias_policy="none",
            declare_threshold=0.90,
            min_samples=8,
        )
        result = choose_arrival_offset(
            prior, config, predicted_restock=20000.0, life_est=360.0
        )
        self.assertGreaterEqual(result["probability"], 0.99)
        self.assertGreater(result["offset_seconds"], 140.0)
        self.assertLess(result["offset_seconds"], 450.0)

    def test_selective_summary_scores_only_declared_predictions(self):
        rows = [
            {
                "actionable_from_anchor": 1,
                "predicted_arrival_success": 0.95,
                "calibration_pool_n": 20,
                "calibration_min_samples": 8,
                "declared_arrival": 1,
                "arrival_hit": 1,
                "early_arrival": 0,
                "late_arrival": 0,
                "absolute_error_seconds": 60,
            },
            {
                "actionable_from_anchor": 1,
                "predicted_arrival_success": 0.91,
                "calibration_pool_n": 20,
                "calibration_min_samples": 8,
                "declared_arrival": 1,
                "arrival_hit": 1,
                "early_arrival": 0,
                "late_arrival": 0,
                "absolute_error_seconds": 90,
            },
            {
                "actionable_from_anchor": 1,
                "predicted_arrival_success": 0.70,
                "calibration_pool_n": 20,
                "calibration_min_samples": 8,
                "declared_arrival": 0,
                "arrival_hit": 0,
                "early_arrival": 1,
                "late_arrival": 0,
                "absolute_error_seconds": 600,
            },
        ]
        s = selective_summary(rows, threshold=0.90)
        self.assertEqual(s["declared_n"], 2)
        self.assertEqual(s["declared_hit_rate"], 1.0)
        self.assertAlmostEqual(s["coverage"], 2 / 3)

    def test_recent_five_cycle_calibration_is_supported(self):
        prior = [{
            "anchor_timestamp": i,
            "actual_restock_timestamp": 10000 + i * 1000,
            "signed_error_seconds": float(i),
            "actual_lifetime_seconds": 300.0,
        } for i in range(10)]
        config = ArrivalStateConfig(
            residual_window=5,
            weighting="linear",
            tod_hours=None,
            bias_policy="none",
            declare_threshold=0.90,
            min_samples=5,
        )
        result = choose_arrival_offset(
            prior, config, predicted_restock=25000.0, life_est=300.0
        )
        self.assertEqual(result["pool_n"], 5)
        self.assertIsNotNone(result["probability"])


if __name__ == "__main__":
    unittest.main()
