"""Causal old-data end-to-end regression with stock-row input immutability."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.historical_restocks_all24 import replay_item, main
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
            self.assertIn("chronological_start_day_slices",result["departure"])
            self.assertGreater(result["physical"]["first_hourly_issues"],0)
            self.assertGreater(result["departure"]["starts"],0)
            self.assertLessEqual(result["last_first_issue"]+28800+
                 model.TRAVEL_SECONDS["mex"]+190,result["source_cutoff"])

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

    def test_rejects_unapproved_scans(self):
        with self.assertRaises(ValueError):
            replay_item("/missing","invented:fake",days=1)
        with self.assertRaises(ValueError):
            replay_item("/missing","mex:Jaguar Plushie",days=90)


if __name__=="__main__":
    unittest.main()
