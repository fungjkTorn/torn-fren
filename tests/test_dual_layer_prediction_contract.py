"""Tests for the offline-only forecast/travel result adapter."""
import unittest

from services.dual_layer_prediction_contract import build_dual_layer_prediction


BASE = {
    "country": "uni",
    "item_name": "Xanax",
    "as_of_timestamp": 10000,
    "observed_quantity": 0,
    "last_observed_timestamp": 9950,
}


class ContractTests(unittest.TestCase):
    def test_stock_forecast_without_travel_plan(self):
        x = build_dual_layer_prediction(
            **BASE,
            forecast={
                "model_name": "mechanical_v2",
                "confidence_label": "good",
                "events": [{
                    "estimated_restock_timestamp": 13000,
                    "restock_window_start_timestamp": 12500,
                    "restock_window_end_timestamp": 13500,
                    "estimated_depletion_timestamp": 15000,
                }],
            },
        )
        self.assertEqual(x["current"]["state"], "sold_out")
        self.assertEqual(x["forecast"]["events"][0]["restock"]["estimate_timestamp"], 13000)
        self.assertIsNone(x["travel"]["recommended_leave_timestamp"])
        self.assertIsNone(x["forecast"]["window_coverage_probability"])

    def test_travel_plan_while_currently_stocked(self):
        x = build_dual_layer_prediction(
            **{**BASE, "observed_quantity": 100},
            travel={
                "model_name": "availability_v21",
                "travel_seconds": 6360,
                "recommended_leave_timestamp": 11000,
                "leave_window_start_timestamp": 10900,
                "leave_window_end_timestamp": 11500,
                "historical_arrival_success_rate": 0.93,
                "historical_evaluation_n": 224,
            },
        )
        self.assertEqual(x["current"]["state"], "active")
        self.assertEqual(x["travel"]["recommended_arrival_timestamp"], 17360)
        self.assertEqual(x["travel"]["wait_seconds"], 1000)
        self.assertIsNone(x["travel"]["probabilities"]["p_arrival"])

    def test_prevent_uncalibrated_probability(self):
        with self.assertRaises(ValueError):
            build_dual_layer_prediction(
                **BASE, travel={"p_arrival": .95, "probabilities_calibrated": False}
            )
        with self.assertRaises(ValueError):
            build_dual_layer_prediction(
                **BASE, forecast={"window_coverage_probability": .90}
            )

    def test_calibrated_and_monotone_probabilities(self):
        x = build_dual_layer_prediction(
            **BASE,
            travel={"probabilities_calibrated": True, "p_arrival": .70,
                    "p_plus_10s": .72, "p_plus_1m": .78, "p_plus_3m": .85},
        )
        self.assertEqual(x["travel"]["probabilities"]["p_plus_3m"], .85)
        with self.assertRaises(ValueError):
            build_dual_layer_prediction(
                **BASE,
                travel={"probabilities_calibrated": True,
                        "p_arrival": .80, "p_plus_10s": .75},
            )

    def test_invalid_windows_and_flight(self):
        with self.assertRaises(ValueError):
            build_dual_layer_prediction(
                **BASE, forecast={"events": [{
                    "estimated_restock_timestamp": 15000,
                    "restock_window_start_timestamp": 16000,
                    "restock_window_end_timestamp": 17000,
                }]}
            )
        with self.assertRaises(ValueError):
            build_dual_layer_prediction(
                **BASE, travel={"travel_seconds": 6360,
                                "recommended_leave_timestamp": 11000,
                                "recommended_arrival_timestamp": 11001}
            )

    def test_partial_stock_and_infeasible_requested_quantity(self):
        x = build_dual_layer_prediction(
            **{**BASE, "observed_quantity": 15},
            data_quality={"historical_max_quantity": 20},
        )
        self.assertEqual(x["current"]["state"], "below_requested_quantity")
        self.assertTrue(any(
            "exceeds historically observed maximum" in w
            for w in x["data_quality"]["warnings"]
        ))

    def test_stale_and_wait_cap_warning(self):
        x = build_dual_layer_prediction(
            **{**BASE, "last_observed_timestamp": 9000},
            travel={"recommended_leave_timestamp": 13000,
                    "max_wait_seconds": 2000, "session_cap": True},
        )
        warnings = x["data_quality"]["warnings"]
        self.assertEqual(len(warnings), 3)
        self.assertTrue(any("stale" in w for w in warnings))
        self.assertTrue(any("wait budget" in w for w in warnings))
        self.assertTrue(any("forced" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
