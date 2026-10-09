"""Frozen Red Fox algorithm routing and future-data safety."""
import unittest
from unittest.mock import patch,Mock
from types import SimpleNamespace
from research import v38_red_fox_single_tick as red

NOW=1791540300


class RedFoxSingleTickTests(unittest.TestCase):
    def test_wrong_item_never_reads_source(self):
        with patch.object(red,"inspect_live_source") as inspector:
            self.assertEqual(red.predict("/no/db","jap","Xanax",NOW)["status"],
                             "NOT_APPROVED_RED_FOX_ANALOG")
            inspector.assert_not_called()

    def test_stale_or_future_source_rejected_before_model(self):
        with patch.object(red,"inspect_live_source",
                          return_value={"status":"FUTURE_RECORDS_PRESENT"}):
            with patch.object(red.ResearchContext,"build") as builder:
                self.assertEqual(red.predict("unused","uni","Red Fox Plushie",NOW)["status"],
                                 "FUTURE_RECORDS_PRESENT")
                builder.assert_not_called()

    def test_k18_and_global_weight_exact_and_causal_query(self):
        context=SimpleNamespace(grid=[NOW],con=Mock())
        with patch.object(red,"inspect_live_source",return_value={"status":"FRESH"}):
            with patch.object(red.ResearchContext,"build",return_value=context):
                with patch.object(red,"AnalogPlanner") as constructor:
                    constructor.return_value.plan.return_value=(NOW+600,.7,.7)
                    out=red.predict("unused","uni","Red Fox Plushie",NOW)
        self.assertEqual(out["status"],"RESEARCH_PROPOSAL_ONLY")
        self.assertEqual(out["recommended_arrival_timestamp"],
                         NOW+600+red.TRAVEL_SECONDS["uni"])
        self.assertEqual(constructor.call_args.kwargs["k"],18)
        self.assertEqual(constructor.call_args.kwargs["global_weight"],0.5)
        self.assertEqual(constructor.call_args.kwargs["cutoff"],NOW)
        self.assertFalse(out["probability_calibrated"])
        self.assertEqual(out["quantity_threshold"],30)
        self.assertEqual(out["grace_seconds"],10)
        context.con.close.assert_called_once()

    def test_lagging_joint_context_abstains(self):
        context=SimpleNamespace(grid=[NOW-900],con=Mock())
        with patch.object(red,"inspect_live_source",return_value={"status":"FRESH"}):
            with patch.object(red.ResearchContext,"build",return_value=context):
                self.assertEqual(red.predict("unused","uni","Red Fox Plushie",NOW)["status"],
                                 "CROSS_ITEM_CONTEXT_LAGGING")


if __name__=="__main__":
    unittest.main()
