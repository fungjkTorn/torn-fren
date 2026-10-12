"""V138 enhanced brief preserves V135 and adds direct original V2 arrival truth."""
import unittest

from research import v138_enhanced_departure_evidence_brief as m

NOW = 1791800000


def fake_base(**kwargs):
    return {
        "status": "V135_HISTORICAL_OLD_GRAPH_AND_NEW_DEPARTURE_BRIEF",
        "asof_epoch": kwargs["now"],
        "collector_and_sidecars_read_only": True,
        "original_graph_v2": {"status": "OLD"},
        "prior_v75": {"status": "V75"},
        "new_v128": {"status": "V128", "departure_timing_quality": {
            "status": "V132", "overall": {}, "per_item": {}
        }},
        "optional_older_research_ledgers": {},
        "limitations": {
            "V75_and_V128_stock_proxy_not_gameplay": True,
        },
    }


def fake_direct(**kwargs):
    return {
        "status": "V137_ORIGINAL_V2_STOCK_AT_ARRIVAL_BENCHMARK",
        "overall": {
            "first_item_UTC_hourly_starts": 10,
            "valid_original_active_targets_under_8h_contract": 8,
            "no_active_target_or_invalid_current_contract": 2,
            "original_active_target_outside_current_8h_contract": 1,
            "stored_recommended_arrival_scorable": 7,
            "stored_recommended_arrival_stock_at_least_30": 5,
            "ui_earliest_action_scorable": 6,
            "ui_earliest_action_stock_at_least_30": 4,
            "ui_earliest_action_stock_below_30": 2,
            "leave_now_scorable": 6,
            "leave_now_stock_at_least_30": 3,
            "leave_now_stock_below_30": 3,
            "matched_ui_vs_leave_now": 6,
            "matched_only_ui_stocked": 2,
            "matched_only_leave_now_stocked": 1,
            "matched_ui_stocked_fraction": 0.6667,
            "matched_leave_now_stocked_fraction": 0.5,
            "ui_minus_leave_now_only_known_pairs": 1,
            "ui_wait_minutes": {"mean": 14.0, "median": 10.0, "max": 40.0},
        },
        "per_item": {
            "uni:Nessie Plushie": {
                "first_item_UTC_hourly_starts": 3,
                "valid_original_active_targets_under_8h_contract": 3,
                "matched_ui_vs_leave_now": 2,
                "ui_earliest_action_stock_at_least_30": 2,
                "leave_now_stock_at_least_30": 1,
                "ui_minus_leave_now_only_known_pairs": 1,
                "ui_wait_minutes": {"mean": 10.0, "median": 10.0, "max": 15.0},
            }
        },
        "selection_exclusions": {"NO_AS_ISSUED_ACTIVE_TARGET": 1},
        "stock_proxy_reason_counts": {"UI_POLL_STATE_PROXY_SUCCESS": 4},
        "method_notes": {"ui_earliest_action": "frozen lower bound"},
        "recent_examples": [],
    }


class V138Tests(unittest.TestCase):
    def test_adds_direct_truth_without_blurring_definitions(self):
        result = m.assemble(
            now=NOW,
            old_v75_days=3,
            new_days=2,
            old_graph_days=30,
            base_brief=fake_base,
            direct_v2=fake_direct,
        )
        self.assertEqual(
            result["status"], "V138_ENHANCED_DEPARTURE_EVIDENCE_BRIEF"
        )
        self.assertTrue(result["collector_and_sidecars_read_only"])
        self.assertEqual(result["base_v135"]["status"],
                         "V135_HISTORICAL_OLD_GRAPH_AND_NEW_DEPARTURE_BRIEF")
        direct = result["original_graph_v2_direct_stock_at_arrival"]
        self.assertEqual(
            direct["status"], "V137_ORIGINAL_V2_STOCK_AT_ARRIVAL_BENCHMARK"
        )
        self.assertEqual(
            direct["overall"]["ui_minus_leave_now_only_known_pairs"], 1
        )
        self.assertTrue(result["comparison_contract"][
            "same_poll_state_proxy_for_original_v2_v75_v128"])
        self.assertFalse(result["comparison_contract"][
            "original_v2_exact_latest_browser_bound_reconstructible"])
        self.assertTrue(result["limitations"][
            "original_v2_direct_arrival_is_poll_state_proxy_not_gameplay"])

    def test_short_summary_calls_out_direct_arrival_section(self):
        base = fake_base(now=NOW)
        # Avoid coupling this unit test to V135's full expected shape.
        old_short = m.v135_short_summary
        try:
            m.v135_short_summary = lambda _base: "BASE V135"
            result = m.assemble(
                now=NOW, base_brief=fake_base, direct_v2=fake_direct
            )
            text = m.short_summary(result)
        finally:
            m.v135_short_summary = old_short
        self.assertIn("BASE V135", text)
        self.assertIn("V138 ORIGINAL V2 DIRECT >=30 ARRIVAL BENCHMARK", text)
        self.assertIn('"matched_ui_vs_leave_now": 6', text)
        self.assertIn("uni:Nessie Plushie", text)
        self.assertIn("No real flight/purchase certification", text)

    def test_refuses_base_that_loses_read_only_contract(self):
        def bad_base(**kwargs):
            value = fake_base(**kwargs)
            value["collector_and_sidecars_read_only"] = False
            return value
        with self.assertRaisesRegex(ValueError, "read-only"):
            m.assemble(now=NOW, base_brief=bad_base, direct_v2=fake_direct)


if __name__ == "__main__":
    unittest.main()
