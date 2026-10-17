"""Diagnose not-actionable median windows when conservative P1..P16 fail."""
import unittest

from research.v150_stock_window_failure_diagnostic import diagnose_window_failure


def state(*,start=1200,late=1700,early_end=1600,med_end=2200,
          issue=500,flight=1100,has_proposal=False):
    return {
        "item_key":"jap:Xanax","issued_epoch":issue,
        "travel_seconds":flight,
        "first_reachable":({"cycle_number":1} if has_proposal else None),
        "status":("PROVISIONAL_FIRST_REACHABLE_STOCK_WINDOW"
                  if has_proposal else "NO_CONSERVATIVE_REACHABLE_WINDOW"),
        "projected_windows":[{
            "cycle_number":1,"type":"PROJECTED_NEW_RESTOCK",
            "expected_start_epoch":start,
            "late_start_epoch":late,
            "expected_end_epoch":med_end,
            "early_end_epoch":early_end,
        }]
    }


class StockWindowFailureTests(unittest.TestCase):
    def test_conservative_bands_disjoint_but_exploratory_median_exists(self):
        r=diagnose_window_failure(state())
        self.assertEqual(r["reason_classification"],
                         "CONSERVATIVE_CROSS_QUANTILE_BANDS_EXCLUDE_MEDIAN_WINDOW")
        alt=r["first_research_only_median_scenario"]
        self.assertEqual(alt["cycle_number"],1)
        self.assertEqual(alt["research_only_wait_seconds"],0)
        self.assertTrue(alt["not_actionable"])
        self.assertFalse(alt["arrival_stock30_certified"])
        self.assertIsNone(alt["calibrated_probability"])
        self.assertFalse(r["exploratory_scenario_actionable"])

    def test_long_flight_without_reachable_median_is_not_a_candidate(self):
        r=diagnose_window_failure(state(flight=5000))
        self.assertEqual(r["reason_classification"],
                         "NEITHER_CONSERVATIVE_NOR_MEDIAN_WINDOW_REACHABLE")
        self.assertIsNone(r["first_research_only_median_scenario"])

    def test_even_existing_conservative_proposal_does_not_certify_success(self):
        r=diagnose_window_failure(state(start=1200,late=1300,
                         early_end=2000,med_end=2300,has_proposal=True))
        self.assertEqual(r["reason_classification"],
                         "V148_ALREADY_HAS_CONSERVATIVE_PROPOSAL")
        self.assertFalse(r["conservative_model_actionable"])

    def test_bogus_window_and_excess_future_cycles_rejected(self):
        bad=state(start=1300,late=1500,early_end=1350,med_end=1200)
        with self.assertRaises(ValueError):
            diagnose_window_failure(bad)
        bad=state()
        bad["projected_windows"]=bad["projected_windows"]*18
        with self.assertRaises(ValueError):
            diagnose_window_failure(bad)


if __name__=="__main__":
    unittest.main()
