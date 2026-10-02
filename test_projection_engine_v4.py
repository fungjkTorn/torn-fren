import unittest

from services.projection_engine_v4 import (
    ItemContext,
    apply_policy,
    point_forecast_pair,
)


class ProjectionEngineV4Tests(unittest.TestCase):
    def _context(self):
        cycles = []
        waits = []
        restock = 0
        for i in range(14):
            depletion = restock + 600
            cycles.append({
                "restock_time": restock,
                "depletion_time": depletion,
                "lifetime_seconds": 600,
                "peak_quantity": 1000,
                "complete": True,
                "tiny_restock": False,
                "valid_lifetime": True,
            })
            if i < 13:
                waits.append({
                    "from_depletion": depletion,
                    "to_restock": depletion + 7200,
                    "seconds": 7200.0,
                })
            restock = depletion + 7200

        return ItemContext(
            country="jap",
            item_name="Synthetic",
            cycles=cycles,
            wait_rows=waits,
            travel_seconds=3600,
            split_timestamp=cycles[10]["depletion_time"],
            max_depth=3,
            min_history=8,
        )

    def test_point_chain_is_reusable_across_policies(self):
        ctx = self._context()
        point = point_forecast_pair(ctx, "all_median", "all_median")
        self.assertTrue(point)

        midpoint = apply_policy(ctx, point, "midpoint", "none")
        late = apply_policy(ctx, point, "late75", "none")

        self.assertEqual(len(midpoint), len(late))
        for a, b in zip(midpoint, late):
            self.assertEqual(
                a["raw_predicted_restock_timestamp"],
                b["raw_predicted_restock_timestamp"],
            )

    def test_depth_two_stays_frozen_from_original_chain(self):
        ctx = self._context()
        point = point_forecast_pair(ctx, "all_median", "all_median")
        rows = apply_policy(ctx, point, "midpoint", "none")

        anchor = ctx.cycles[8]["depletion_time"]
        anchor_rows = [r for r in rows if r["anchor_timestamp"] == anchor]
        p2 = next(r for r in anchor_rows if r["depth"] == 2)

        expected = anchor + 7200 + 600 + 7200
        self.assertEqual(p2["raw_predicted_restock_timestamp"], expected)


if __name__ == "__main__":
    unittest.main()
