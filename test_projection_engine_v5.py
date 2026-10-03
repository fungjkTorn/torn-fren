import unittest

from services.projection_engine_v4 import ItemContext
from services.projection_engine_v5 import (
    BridgeConfig,
    _known_spacing_rows,
    bridge_point_forecast,
)


class ProjectionEngineV5Tests(unittest.TestCase):
    def _ctx(self):
        cycles=[]
        waits=[]
        restock=0
        for i in range(16):
            depletion=restock+600
            cycles.append({
                "restock_time":restock,
                "depletion_time":depletion,
                "lifetime_seconds":600,
                "peak_quantity":1000,
                "complete":True,
                "tiny_restock":False,
                "valid_lifetime":True,
                "_valid_for_training":True,
            })
            if i<15:
                waits.append({
                    "from_depletion":depletion,
                    "to_restock":depletion+7200,
                    "seconds":7200.0,
                })
            restock=depletion+7200
        return ItemContext(
            country="arg", item_name="Synthetic",
            cycles=cycles, wait_rows=waits,
            travel_seconds=3600,
            split_timestamp=cycles[12]["depletion_time"],
            max_depth=4, min_history=8,
        )

    def test_spacing_history_is_past_only(self):
        ctx=self._ctx()
        anchor_i=10
        anchor_ts=ctx.cycles[anchor_i]["depletion_time"]
        rows=_known_spacing_rows(ctx.cycles, anchor_i, anchor_ts)
        self.assertTrue(rows)
        self.assertTrue(all(r["to_restock"] <= anchor_ts for r in rows))

    def test_direct_spacing_does_not_use_lifetime_for_bridge(self):
        ctx=self._ctx()
        cfg=BridgeConfig(
            "direct_spacing",
            wait_method="all_median",
            spacing_method="all_median",
        )
        rows=bridge_point_forecast(ctx,"all_median",cfg)
        anchor=ctx.cycles[10]["depletion_time"]
        d2=next(
            r for r in rows
            if r["anchor_timestamp"]==anchor and r["depth"]==2
        )
        # P1: +7200. Direct spacing to P2: +7800.
        self.assertEqual(
            d2["raw_predicted_restock_timestamp"],
            anchor + 7200 + 7800,
        )

    def test_hybrid_half_blends_bridge(self):
        ctx=self._ctx()
        cfg=BridgeConfig(
            "hybrid",
            wait_method="all_median",
            spacing_method="all_median",
            direct_weight=0.50,
        )
        rows=bridge_point_forecast(ctx,"all_median",cfg)
        anchor=ctx.cycles[10]["depletion_time"]
        d2=next(
            r for r in rows
            if r["anchor_timestamp"]==anchor and r["depth"]==2
        )
        # decomposition bridge 600+7200 = 7800; direct spacing = 7800.
        self.assertEqual(
            d2["raw_predicted_restock_timestamp"],
            anchor + 7200 + 7800,
        )


if __name__ == "__main__":
    unittest.main()
