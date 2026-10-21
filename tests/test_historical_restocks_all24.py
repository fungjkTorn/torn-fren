"""Causal old-data end-to-end regression with stock-row input immutability."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.historical_restocks_all24 import replay_item, main, illustrative_flight_evidence
from research.restock_event_clock import model
from test_continuous_departure_replay import ContinuousTests


class HistoricalAll24Tests(unittest.TestCase):
    def test_historical_maturity_and_flight_against_leave_now(self):
        with tempfile.TemporaryDirectory() as td:
            source=ContinuousTests().fixture(Path(td))
            before=source.read_bytes()
            result=replay_item(source,"mex:Jaguar Plushie",days=1)
            self.assertEqual(source.read_bytes(),before)
            self.assertEqual(result["issued_every_seconds"],300)
            self.assertEqual(result["threshold"],30)
            self.assertTrue(result["arrival_plus_10_seconds"])
            self.assertTrue(result["no_future_training"])
            self.assertFalse(result["auto_promoted"])
            self.assertIn("later_untuned",result["physical"])
            self.assertIn("leave_now",result)
            self.assertIn("matched_vs_now",result)
            proof=result["flight_evidence_examples"]
            self.assertTrue(proof["source_observations_truncated_for_model"])
            self.assertTrue(proof["future_observations_used_only_to_score"])
            self.assertEqual(proof["replan_cadence_seconds"],300)
            self.assertEqual(proof["grace_seconds"],10)
            for status,example in proof["outcome_examples"].items():
                self.assertEqual(example["result"],status)
                self.assertFalse(example["actual_player_flight"])
                self.assertEqual(example["arrival_plus_10_epoch"],
                                 example["simulated_landing_epoch"]+10)
                self.assertLessEqual(example["last_reconfirmation_epoch"],
                                     example["simulated_departure_epoch"])
            self.assertIn("chronological_start_day_slices",result["departure"])
            self.assertGreater(result["physical"]["first_hourly_issues"],0)
            self.assertGreater(result["departure"]["starts"],0)
            self.assertLessEqual(result["last_first_issue"]+28800+
                 model.TRAVEL_SECONDS["mex"]+190,result["source_cutoff"])

    def test_concrete_historical_flight_examples_show_polls_and_quantities(self):
        plans=[(t,t+15,2) for t in range(3600,4*3600,300)]
        arrivals=[]
        def independent_scoring(arrival):
            arrivals.append(arrival)
            if arrival<6000:
                return "SUCCESS","POLL_BACKED_DELTA_STATE",dict(
                    pre_poll=arrival-15,post_poll=arrival+25,
                    pre_quantity=1000,post_quantity=995,
                    item_provider="yata")
            if arrival<10000:
                return "FAILURE","POLL_BACKED_DELTA_STATE",dict(
                    pre_poll=arrival-10,post_poll=arrival+20,
                    pre_quantity=0,post_quantity=0,
                    item_provider="yata")
            return "UNKNOWN","NO_POLL_BRACKET",None
        proof=illustrative_flight_evidence(
            plans,score=independent_scoring,flight_seconds=1020,
            cutoff=20000,start_before=10800)
        self.assertEqual(len(arrivals),3)
        self.assertEqual(set(proof["outcome_examples"]),
                         {"SUCCESS","FAILURE","UNKNOWN"})
        good=proof["outcome_examples"]["SUCCESS"]
        self.assertEqual(good["historical_quantity_at_pre_poll"],1000)
        self.assertEqual(good["historical_quantity_at_post_poll"],995)
        self.assertEqual(good["simulated_departure_epoch"],3615)
        self.assertEqual(good["simulated_landing_epoch"],4635)
        self.assertEqual(good["arrival_plus_10_epoch"],4645)
        self.assertEqual(proof["outcome_examples"]["FAILURE"]
                         ["historical_quantity_at_post_poll"],0)
        self.assertIsNone(proof["outcome_examples"]["UNKNOWN"]
                          ["historical_quantity_at_post_poll"])
        self.assertIn("NOT_REPRESENTATIVE",proof["selection"])

    def test_no_advance_leakage_in_example_reconfirmations(self):
        seen=[]
        plans=[(t,t+200,1) for t in range(3600,7500,300)]
        # Only the freshest issue may authorize immediate departure.
        def score(at):
            seen.append(at)
            return "SUCCESS","POLL_BACKED_DELTA_STATE",dict(
                pre_quantity=50,post_quantity=48,pre_poll=at-2,
                post_poll=at+12,item_provider="yata")
        proof=illustrative_flight_evidence(
            plans,score=score,flight_seconds=1020,
            cutoff=50000,start_before=7200)
        self.assertEqual(set(proof["outcome_examples"]),{"SUCCESS"})
        self.assertEqual(len(seen),2)
        self.assertEqual(proof["outcome_examples"]["SUCCESS"]
                         ["last_reconfirmation_epoch"],3600)

    def test_source_future_mutation_cannot_change_preissue_forecast(self):
        from research.true_zero_cycles import ZeroCycles
        from research.restock_event_clock import continuous_source
        from services.travel_decision_contract_v166 import build_item_travel_decision
        from test_continuous_departure_replay import T
        rows=[model.OBS(T-10000,0,"p")]
        for i in range(60):
            at=T+i*2400
            rows.extend([model.OBS(at,180,"p"),
                         model.OBS(at+700,20,"p"),
                         model.OBS(at+1000,0,"p")])
        issued=T+51*2400+10
        def predict(src):
            z=ZeroCycles(continuous_source(src,lambda a,b:False))
            for row in src:
                if row.epoch<=issued:z.add(row)
            forecast=z.forecast("mex:Jaguar Plushie",asof=issued)
            return build_item_travel_decision(forecast,now=issued,poll_age_seconds=1)
        first=predict(rows)
        mutated=[row if row.epoch<=issued else model.OBS(row.epoch,0,row.source)
                 for row in rows]
        self.assertEqual(first,predict(mutated))

    def test_failing_item_is_reported_without_claiming_complete_roster(self):
        import json
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/"failed-historical.json"
            argv=["historical_restocks_all24","--source","/not-read",
                  "--output",str(out),"--model-sha","a"*40,
                  "--days","1","--item-key","mex:Jaguar Plushie"]
            with patch("sys.argv",argv), patch(
                    "research.historical_restocks_all24.replay_item",
                    side_effect=ValueError("synthetic bad item")):
                main()
            report=json.loads(out.read_text())
            self.assertEqual(report["run_status"],"PARTIAL_NO_PROMOTION")
            self.assertEqual(report["completed_items"],0)
            self.assertIn("mex:Jaguar Plushie",report["failed_items"])
            self.assertFalse(report["automatic_model_promotion"])

    def test_rejects_unapproved_scans(self):
        with self.assertRaises(ValueError):
            replay_item("/missing","invented:fake",days=1)
        with self.assertRaises(ValueError):
            replay_item("/missing","mex:Jaguar Plushie",days=90)


if __name__=="__main__":
    unittest.main()
