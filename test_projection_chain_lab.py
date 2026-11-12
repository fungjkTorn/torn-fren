import unittest

from services.projection_chain_lab import Strategy, _score_strategy


class ProjectionChainLabTests(unittest.TestCase):
    def test_p2_is_frozen_from_original_anchor(self):
        cycles = [
            {"restock_time": 0, "depletion_time": 600, "lifetime_seconds": 600},
            {"restock_time": 7800, "depletion_time": 8400, "lifetime_seconds": 600},
            {"restock_time": 15600, "depletion_time": 16200, "lifetime_seconds": 600},
            {"restock_time": 23400, "depletion_time": 24000, "lifetime_seconds": 600},
            {"restock_time": 31200, "depletion_time": 31800, "lifetime_seconds": 600},
            {"restock_time": 39000, "depletion_time": 39600, "lifetime_seconds": 600},
            {"restock_time": 46800, "depletion_time": 47400, "lifetime_seconds": 600},
            {"restock_time": 54600, "depletion_time": 55200, "lifetime_seconds": 600},
            {"restock_time": 62400, "depletion_time": 63000, "lifetime_seconds": 600},
            # Future cycle #1 is late by 10 minutes versus history.
            {"restock_time": 70800, "depletion_time": 71400, "lifetime_seconds": 600},
            # Future cycle #2 stays on the shifted schedule.
            {"restock_time": 78600, "depletion_time": 79200, "lifetime_seconds": 600},
        ]
        waits = {
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

        rows = _score_strategy(
            cycles,
            waits,
            Strategy("all_median", "all_median"),
            max_depth=2,
            min_history=8,
        )

        anchor_rows = [r for r in rows if r["anchor_timestamp"] == 63000]
        self.assertEqual(len(anchor_rows), 2)

        p1 = next(r for r in anchor_rows if r["depth"] == 1)
        p2 = next(r for r in anchor_rows if r["depth"] == 2)

        self.assertEqual(p1["predicted_restock_timestamp"], 70200)
        self.assertEqual(p1["actual_restock_timestamp"], 70800)
        # P2 remains the original 63,000-anchor projection. It is NOT rebuilt
        # from the later real 70,800 restock.
        self.assertEqual(p2["predicted_restock_timestamp"], 78000)
        self.assertEqual(p2["actual_restock_timestamp"], 78600)
        self.assertEqual(p2["signed_error_seconds"], 600)


if __name__ == "__main__":
    unittest.main()
