"""V135 combines old V2, V75, V128, timing without conflating truth."""
import unittest
from research import v135_morning_departure_brief as m


class MorningEvidenceBriefTests(unittest.TestCase):
    def test_distinct_sources_never_collapse_to_one_accuracy(self):
        original={
            "status":"V134_ORIGINAL_GRAPH_PREDICTION_V2_RECORDED_AUDIT",
            "overall":{
                "resolved_valid_target_cycles":4,
                "observed_restock_window_hit_rate":0.75},
            "per_projection_depth":{},
            "per_item":{"uni:Nessie Plushie":{
                "selected_first_issued_active_item_hours":4,
                "resolved_valid_target_cycles":4,
                "observed_restock_window_hit_rate":0.75,
                "arrival_inside_target_cycle_rate":0.5}},
            "24_item_first_issued_active_UTC_hours":4,
        }
        old={
            "all_24_roster_count":24,
            "older_sidecar_inventory":{},
            "old_V75":{"status":"OLD_FORECASTS","summary":{
                "matched_only_old_model_stocked":1,
                "matched_only_leave_now_stocked":2
            },"per_item":{"uni:Nessie Plushie":{
                "first_item_UTC_hourly_starts":5,
                "matched_flight_outcomes":4,
                "model_minus_now_only_known_pairs":-1}}},
            "new_V128":{"status":"V129_24","raw_five_minute_rows":24,
                "first_issued_item_hour_cohorts":24,
                "summary":{"proposed_departure_hours":14},
                "per_item":{"uni:Nessie Plushie":{
                    "first_issue_UTC_item_hours":1,
                    "model_proxy_success":0,
                    "model_proxy_miss":0}}},
        }
        timing={
            "status":"V132_TIMING_QUALITY",
            "all_24_items":24,
            "overall":{"issued_five_minute_snapshots":24,
                       "issued_future_watches_not_executable":4,
                       "reconfirmation_counts_for_first_hour_proposals":{}},
            "per_item":{"uni:Nessie Plushie":{
                "issued_five_minute_snapshots":1,
                "issued_future_watches_not_executable":1,
                "mean_proposed_wait_minutes":20,
                "maturity_counts_for_first_hour_proposals":{}
            }},
        }
        def f1(**kwargs):
            self.assertEqual(kwargs["asof"],10000)
            return old
        def f2(**kwargs):
            self.assertEqual(kwargs["now"],10000)
            return timing
        def f3(**kwargs):
            self.assertEqual(kwargs["asof"],10000)
            return original
        result=m.assemble(
            now=10000,old_graph_days=30,
            multiple_ledger=f1,timing=f2,oldgraph=f3)
        self.assertEqual(result["status"],
                         "V135_HISTORICAL_OLD_GRAPH_AND_NEW_DEPARTURE_BRIEF")
        self.assertEqual(result["original_graph_v2"]["overall"][
            "observed_restock_window_hit_rate"],.75)
        self.assertEqual(result["prior_v75"]["overall"][
            "matched_only_leave_now_stocked"],2)
        self.assertEqual(result["new_v128"][
            "observed_30_stock_arrival_proxy"]["proposed_departure_hours"],14)
        self.assertFalse(result["collector_and_sidecars_read_only"] is False)
        self.assertTrue(result["limitations"][
            "original_graph_restock_cycle_hit_not_verified_30_stock_at_arrival"])
        text=m.short_summary(result)
        self.assertIn("ORIGINAL GRAPH V2",text)
        self.assertIn("OLD V75",text)
        self.assertIn("V128",text)
        self.assertIn("uni:Nessie Plushie",text)
        self.assertIn('"v128_future_watches": 1',text)
        self.assertIn('"v75_model_only_vs_leave_now_only_net": -1',text)

    def test_roster_guard_never_credits_partial_ledger(self):
        with self.assertRaisesRegex(ValueError,"exact 24"):
            m.assemble(now=1,
                multiple_ledger=lambda **x:{
                    "all_24_roster_count":23},
                timing=lambda **x:{"all_24_items":24},
                oldgraph=lambda **x:{"status":"NO_SOURCE"})


if __name__=="__main__":
    unittest.main()
