"""Prove V18-20 native plans are correctly labeled PREVIEW, not next restock."""
import copy
import unittest

from research.v2_native_specialist_adapter import (
    registered_models, preview_record, model_integration_inventory)
from research.v97_experimental_dashboard_state import classify_prediction
from research.v2_beta_departure_bridge import build_item_timeline
from research.plushie_champions.common import TRAVEL_SECONDS

ISSUE = 1791800000

def plan(item_key="can:Crocus", delay=600, score=.65, support=15):
    country=item_key.partition(":")[0]
    return {
        "query_time": float(ISSUE),
        "departure_time": float(ISSUE+delay),
        "arrival_time": float(ISSUE+delay+TRAVEL_SECONDS[country]),
        "probability": score,
        "support": support,
    }

class NativeArrivalPlanAdapterTests(unittest.TestCase):
    def test_every_native_item_supported_and_rest_unverified(self):
        models=registered_models()
        self.assertEqual(len(models),16)
        inv=model_integration_inventory()
        self.assertEqual(len(inv),24)
        self.assertEqual(sum(x["native_preview_adapter_supported"] for x in inv.values()),16)
        self.assertEqual(sum(x["capability"]=="REPLAY_CHAMPION_LIVE_ADAPTER_UNVERIFIED"
                             for x in inv.values()),7)
        self.assertEqual(inv["jap:Xanax"]["capability"],
                         "JAPAN_SPECIALIST_DEPLOYED_SOURCE_UNVERIFIED")
        self.assertTrue(all(not x["arrival_stock_accuracy_verified"]
                            for x in inv.values()))

    def test_true_original_v18_plan_into_existing_preview_status(self):
        original=plan()
        old=copy.deepcopy(original)
        row=preview_record("can:Crocus",original,family="V18",
                           config="dyn5",issued_at=ISSUE,stock_as_of=ISSUE-20)
        self.assertEqual(original,old)
        self.assertEqual(row["departure"],ISSUE+600)
        self.assertEqual(row["arrival"],ISSUE+600+1620)
        self.assertEqual(row["raw_model_availability_score"],.65)
        self.assertEqual(row["status"],"RESEARCH_PREVIEW_UNVALIDATED")
        self.assertFalse(row["actionable"])
        self.assertFalse(row["prediction_accuracy_verified"])
        self.assertFalse(row["probability_calibrated"])
        self.assertEqual(row["valid_until"],ISSUE+300)
        self.assertIn("NOT_RESTOCK",row["source_interpretation"])
        state=classify_prediction(row,now=ISSUE+60)
        self.assertEqual(state["display_state"],"UNVALIDATED_RESEARCH_PREVIEW")
        self.assertEqual(state["departure_time"],ISSUE+600)

    def test_v19_and_v20_and_generic_xanax(self):
        for item, family, config in (
            ("can:Xanax","V19","dyn8"),
            ("uni:Xanax","V19","dyn3"),
            ("chi:Peony","V20","traj12"),
        ):
            with self.subTest(item=item):
                row=preview_record(item,plan(item),family=family,config=config,
                                   issued_at=ISSUE,stock_as_of=ISSUE-10)
                self.assertEqual(row["model_family"],family)
                self.assertEqual(row["model_config"],config)
                self.assertEqual(row["arrival"]-row["departure"],
                                 TRAVEL_SECONDS[item.split(":")[0]])

    def test_blank_output_is_explicit_abstention(self):
        row=preview_record("can:Crocus",None,family="V18",config="dyn5",
                           issued_at=ISSUE,stock_as_of=ISSUE-10)
        self.assertEqual(row["status"],"RESEARCH_PREVIEW_ABSTAINED")
        self.assertIsNone(row["departure"])
        self.assertFalse(row["actionable"])

    def test_unsupported_champion_cannot_be_forced_through_v18(self):
        with self.assertRaises(ValueError):
            preview_record("uni:Nessie Plushie",plan("uni:Nessie Plushie"),
                           family="V18",config="dyn5",issued_at=ISSUE,
                           stock_as_of=ISSUE-10)
        with self.assertRaises(ValueError):
            preview_record("can:Crocus",plan(),family="V19",config="dyn5",
                           issued_at=ISSUE,stock_as_of=ISSUE-10)

    def test_fail_closed_on_future_leaks_and_invalid_times(self):
        good=plan()
        for changes in (
            {"query_time":ISSUE+1},
            {"departure_time":ISSUE-1},
            {"departure_time":ISSUE+301,
             "arrival_time":ISSUE+301+1620},
            {"departure_time":ISSUE+29000,
             "arrival_time":ISSUE+29000+1620},
            {"arrival_time":ISSUE+600+1060},
        ):
            with self.subTest(changes=changes):
                bad={**good,**changes}
                with self.assertRaises(ValueError):
                    preview_record("can:Crocus",bad,family="V18",
                                   config="dyn5",issued_at=ISSUE,
                                   stock_as_of=ISSUE-10)

    def test_score_is_uncalibrated_and_invalid_score_rejected(self):
        for value in (-.01,1.01,float("nan"),True,None):
            with self.subTest(score=value):
                with self.assertRaises(ValueError):
                    preview_record("can:Crocus",plan(score=value),
                                   family="V18",config="dyn5",
                                   issued_at=ISSUE,stock_as_of=ISSUE-10)

    def test_source_must_be_recent_at_issuance(self):
        with self.assertRaises(ValueError):
            preview_record("can:Crocus",plan(),family="V18",config="dyn5",
                           issued_at=ISSUE,stock_as_of=ISSUE-181)

    def test_shared_v2_timeline_preserves_both_views(self):
        native=preview_record("can:Crocus",plan(),family="V18",config="dyn5",
                              issued_at=ISSUE,stock_as_of=ISSUE-20)
        out=build_item_timeline("can:Crocus",{"predictions":[]},
             now=ISSUE+40,issued_at=ISSUE,stock_as_of=ISSUE-20,
             incumbent=native)
        self.assertIsNone(out["next_predicted_restock"])
        self.assertEqual(out["incumbent_specialist"]["departure_epoch"],ISSUE+600)
        self.assertEqual(out["incumbent_specialist"]["model_family"],"V18")
        self.assertIsNone(out["first_reachable"])
        self.assertFalse(out["incumbent_specialist"]["verified_stock_at_arrival"])
        self.assertIn("country=can",out["v2_graph_url"])

if __name__=="__main__":
    unittest.main()
