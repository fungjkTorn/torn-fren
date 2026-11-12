"""24-item scorecard must show honest sample sizes and all roster items."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/"deploy/scripts/v161_forward_24item_scorecard.py"
spec=importlib.util.spec_from_file_location("v161_scorecard",PATH)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def fixture():
    items={}
    for i in range(24):
        items[f"can:Item {i:02}"]={
            "independent_hit":3 if i<12 else 0,
            "independent_miss":1 if i<12 else 0,
            "independent_pending":1,
            "independent_unknown":0,
            "independent_abstain":0,
            "paired_complete_hit":2 if i<12 else 0,
            "paired_complete_miss":2 if i<12 else 0,
            "paired_complete_pending":2,
            "paired_complete_unknown":0,
            "paired_complete_abstain":0,
            "issued_item_hours":5,
            "unique_issued_stock_phases":1}
    return {
        "status":"V161_TRUE_PROSPECTIVE_V151_24_ITEM_SHADOW_REPORT",
        "roster_size":24,
        "historically_reconstructed_issues":False,
        "issued_item_hours":120,
        "recorded_five_minute_item_rows":1104,
        "totals":{"independent_hit":36,"independent_miss":12,
                  "independent_pending":24,"independent_unknown":0,
                  "paired_complete_hit":24,"paired_complete_miss":24,
                  "paired_complete_pending":48,"paired_complete_unknown":0},
        "items":items}

class ScorecardTests(unittest.TestCase):
    def test_all_24_and_denominators(self):
        output=module.scorecard(fixture())
        self.assertIn("75.0% (36/48)",output)
        self.assertIn("50.0% (24/48)",output)
        self.assertIn("75.0% (3/4)",output)
        self.assertIn("50.0% (2/4)",output)
        self.assertIn("n/a",output)
        self.assertIn("can:Item 00",output)
        self.assertIn("can:Item 23",output)
        self.assertIn("not a guarantee",output.lower())
        self.assertIn("CHANGES",output.upper())
        self.assertEqual(sum("can:Item " in l for l in output.splitlines()),24)
    def test_refuses_historical_or_incomplete_roster(self):
        bad=fixture()
        bad["historically_reconstructed_issues"]=True
        with self.assertRaisesRegex(ValueError,"not the actual prospective"):
            module.scorecard(bad)
        bad=fixture()
        bad["items"].pop("can:Item 23")
        with self.assertRaisesRegex(ValueError,"not the actual prospective"):
            module.scorecard(bad)
    def test_rate_handles_zero_mature_samples(self):
        self.assertEqual(module.pct(0,0),"n/a")
        self.assertEqual(module.pct(45,16),"73.8% (45/61)")
        self.assertEqual(module.pct(45,17),"72.6% (45/62)")

if __name__=="__main__":
    unittest.main()
