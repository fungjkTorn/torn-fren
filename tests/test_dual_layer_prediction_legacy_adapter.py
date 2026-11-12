"""Check that the existing V2 display forecast maps safely into V3."""
import unittest

from services.dual_layer_prediction_legacy_adapter import from_legacy_v2


class LegacyAdapterTest(unittest.TestCase):
    def test_forecast_kept_separate_from_leave_by(self):
        x = from_legacy_v2(
            country="uni", item_name="Xanax", as_of_timestamp=10000,
            last_observed_timestamp=9980,
            prediction_v2={
                "status": "using_reachable_cycle", "current_stock": 0,
                "arrival_success_rate": .91,
                "predictions": [{
                    "estimate_timestamp": 17000,
                    "window_start_timestamp": 16000,
                    "window_end_timestamp": 18000,
                    "target_depletion_timestamp": 21000,
                    "recommended_arrival_timestamp": 17600,
                    "recommended_leave_by_timestamp": 11240,
                    "travel_seconds": 6360,
                    "travel_reliability": "good",
                    "model_name": "median_v2",
                }],
            },
        )
        self.assertEqual(x["forecast"]["events"][0]["restock"]["estimate_timestamp"], 17000)
        self.assertEqual(x["forecast"]["events"][0]["depletion"]["estimate_timestamp"], 21000)
        self.assertEqual(x["travel"]["leave_by_timestamp"], 11240)
        self.assertIsNone(x["travel"]["recommended_leave_timestamp"])
        self.assertIsNone(x["travel"]["probabilities"]["p_arrival"])
        self.assertEqual(x["travel"]["historical_arrival_success_rate"], .91)

    def test_gap_anchor_is_not_silently_high_confidence(self):
        x = from_legacy_v2(
            country="jap", item_name="Xanax", as_of_timestamp=10000,
            last_observed_timestamp=9900,
            prediction_v2={"status": "waiting_for_clean_anchor", "current_stock": 0,
                           "caution_only": True},
        )
        self.assertEqual(len(x["forecast"]["events"]), 0)
        self.assertTrue(any("anchor" in w for w in x["data_quality"]["warnings"]))


if __name__ == "__main__":
    unittest.main()
