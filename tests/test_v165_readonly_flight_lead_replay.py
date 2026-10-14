"""V165 flight-lead audit: no hindsight in features or candidate selection."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deploy.scripts import v165_readonly_flight_lead_replay as m
from research.v128_full24_earliest_shadow import exact_roster

ASOF=1791911000


class FlightLeadAuditTests(unittest.TestCase):
    def test_candidate_uses_issue_computable_arrival_reference_only(self):
        forecast={"restock_events":[
            {"predicted_restock_epoch":10000,"expected_departure_epoch":9800},
            {"predicted_restock_epoch":10300,"expected_departure_epoch":10100},
            {"predicted_restock_epoch":14500,"expected_departure_epoch":13000},
        ]}
        pick=m.select_restock_for_arrival(forecast,reference_arrival=10200)
        self.assertEqual(pick["predicted_restock_epoch"],10300)
        self.assertIsNone(m.select_restock_for_arrival(
            forecast,reference_arrival=19000))
        with self.assertRaises(ValueError):
            m.select_restock_for_arrival(forecast,reference_arrival=100,
                                        max_deviation=9000)

    def test_24_item_historical_flight_lead_audit_is_causal_and_read_only(self):
        from test_v160_prospective_v151_shadow import collector_fixture
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            db=collector_fixture(root,issued=ASOF)
            # Match the V163 fixture's provider-consistent cycles.
            start=(ASOF-3*86400)//1200*1200
            with sqlite3.connect(db) as cx:
                for key in exact_roster():
                    country,item=key.split(":",1)
                    cx.executemany(
                        """INSERT INTO stock_history(timestamp,quantity,source,country,item_name)
                           VALUES(?,?,?,?,?)""",
                        [(start+i*1200+offset,qty,"yata",country,item)
                         for i in range(216)
                         for offset,qty in ((0,0),(600,200),(900,0))])
            pre=db.read_bytes()
            observed_issued=[]
            original=m.model.predict_events
            def trace(item,phase,*,asof,**kwargs):
                self.assertLessEqual(phase["last_observation"].epoch,asof)
                self.assertTrue(all(x>0 for x in phase["stocked_durations"]))
                self.assertTrue(all(x>0 for x in phase["depleted_durations"]))
                observed_issued.append(asof)
                return original(item,phase,asof=asof,**kwargs)
            with patch.object(m.model,"predict_events",side_effect=trace):
                report=m.score_flight_lead(
                    source=db,roster=exact_roster(),asof=ASOF,days=1,
                    limit_items=2)
            self.assertEqual(db.read_bytes(),pre)
            self.assertEqual(report["items_evaluated"],2)
            self.assertTrue(report["future_truth_chooses_evaluation_issue_only"])
            self.assertFalse(report["candidate_selection_uses_true_restock_timestamp"])
            self.assertFalse(report["genuine_live_issuance"])
            self.assertFalse(report["event_precision_measured"])
            self.assertFalse(report["departure_success_measured"])
            self.assertFalse(report["arrival_stock_success_measured"])
            self.assertTrue(observed_issued)
            self.assertTrue(all(x%300==0 for x in observed_issued))
            for policy,stats in report["policies"].items():
                self.assertGreater(stats["observed_restocks"],2)
                self.assertLessEqual(stats["candidate_count"],
                                     stats["observed_restocks"])
                self.assertLessEqual(stats["matched_at_15s"],
                                     stats["matched_at_60s"])
                self.assertLessEqual(stats["matched_at_60s"],
                                     stats["matched_at_10m"])
                self.assertLessEqual(stats["matched_at_10m"],
                                     stats["observed_restocks"])
                self.assertEqual(sum(v["policies"][policy]["matched_at_60s"]
                     for v in report["items"].values()),stats["matched_at_60s"])
            with self.assertRaises(ValueError):
                m.score_flight_lead(source=db,roster=exact_roster(),
                                    asof=ASOF,days=15)

if __name__=="__main__":
    unittest.main()
