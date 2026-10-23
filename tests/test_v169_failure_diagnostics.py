"""Synthetic V169 final-report semantics and retention regression."""
import json
import tempfile
import unittest
from pathlib import Path

from research.v169_failure_diagnostics import classify_execution, analyze_folder


class V169FailureDiagnosticsTests(unittest.TestCase):
    def test_arrive_stocked_is_success_even_before_future_target_restock(self):
        self.assertEqual(classify_execution({
            "arrival_state":"SUCCESS",
            "arrival_epoch":10000,
            "actual_target_restock_epoch":10200,
            "actual_target_status":"EARLIEST_REACHABLE_FOUND",
        }),"STOCKED_ARRIVAL_SUCCESS")

    def test_known_failure_modes_and_unknown_are_distinct(self):
        template={"arrival_epoch":10000,"arrival_state":"FAILURE",
                  "actual_target_status":"EARLIEST_REACHABLE_FOUND"}
        self.assertEqual(classify_execution(dict(template,actual_target_restock_epoch=10500)),
                         "EARLY_MISS_BEFORE_NEAR_RESTOCK")
        self.assertEqual(classify_execution(dict(template,actual_target_restock_epoch=12000)),
                         "BEFORE_TARGETED_RESTOCK_NOT_NEAR")
        self.assertEqual(classify_execution(dict(template,actual_target_restock_epoch=9000)),
                         "STOCK_MISS_AFTER_TARGETED_RESTOCK")
        self.assertEqual(classify_execution(dict(template,actual_target_status=
            "CURRENT_STOCK_ALREADY_GE30",actual_target_restock_epoch=None)),
            "CURRENT_STOCK_WINDOW_EXPIRED_BEFORE_LANDING")
        self.assertEqual(classify_execution({"arrival_state":"UNKNOWN"}),
                         "UNKNOWN_STOCK_AT_LANDING")

    def test_aggregate_does_not_rewrite_original_summary_or_inflate_accuracy(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            summary=dict(results={
                "sou:Xanax":{"status":"ERROR_EXIT_1"},
                "uni:Red Fox Plushie":{"status":"COMPLETED"}})
            (root/"summary.json").write_text(json.dumps(summary))
            observations=[
                dict(arrival_state="SUCCESS",arrival_epoch=5000,
                     actual_target_restock_epoch=5050,
                     actual_target_status="EARLIEST_REACHABLE_FOUND"),
                dict(arrival_state="FAILURE",arrival_epoch=6000,
                     actual_target_restock_epoch=6100,
                     actual_target_status="EARLIEST_REACHABLE_FOUND"),
                dict(arrival_state="FAILURE",arrival_epoch=7000,
                     actual_target_restock_epoch=None,
                     actual_target_status="CURRENT_STOCK_ALREADY_GE30"),
                dict(arrival_state="UNKNOWN",arrival_epoch=8000),
            ]
            data=dict(item_key="uni:Red Fox Plushie",
                      actionable_executions=observations,
                      execution_counts=dict(executions=4,arrival_success=1,
                                            arrival_known=3))
            (root/"uni__Red_Fox_Plushie.json").write_text(json.dumps(data))
            original=(root/"summary.json").read_bytes()
            results=analyze_folder(root)
            self.assertEqual((root/"summary.json").read_bytes(),original)
            self.assertEqual(results["completed_items"],1)
            self.assertEqual(results["failed_items"],["sou:Xanax"])
            self.assertEqual(results["outcomes"]["STOCKED_ARRIVAL_SUCCESS"],1)
            self.assertEqual(results["outcomes"]["EARLY_MISS_BEFORE_NEAR_RESTOCK"],1)
            self.assertEqual(results["outcomes"]["CURRENT_STOCK_WINDOW_EXPIRED_BEFORE_LANDING"],1)
            self.assertEqual(results["outcomes"]["UNKNOWN_STOCK_AT_LANDING"],1)
            self.assertFalse(results["production_modified"])

    def test_mismatched_denominators_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"summary.json").write_text(json.dumps(dict(results={
                "sou:Xanax":{"status":"COMPLETED"}})))
            (root/"sou__Xanax.json").write_text(json.dumps(dict(
                item_key="sou:Xanax",actionable_executions=[
                    {"arrival_state":"SUCCESS"}],
                execution_counts={"executions":1,"arrival_known":1,"arrival_success":0})))
            with self.assertRaisesRegex(ValueError,"success count disagreement"):
                analyze_folder(root)


if __name__=="__main__":
    unittest.main()
