"""Offline synthetic tests for V32 postfreeze scorer; zero collector writes."""
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research.v32_score_shadow import arrival_truth, score_capture
from research.v31_shadow_evidence_capture import record_private_decision

BASE=1800000000


def snapshot(now,dep=None,arr=None):
    ok=dep is not None
    return {
      "schema":"torn-fren-private-research-shadow-v29",
      "mode":"READ_ONLY_DIAGNOSTIC",
      "generated_at":now,
      "default_live_routing":"UNCHANGED",
      "key":"can:Fire Hydrant",
      "candidate_promoted":False,"chance_calibrated":False,
      "candidate_model_family":"v21","candidate_config":"dyn13",
      "champion_executed":ok,
      "baseline":{"status":"unavailable"},
      "challenger":{"status":"RESEARCH_PROPOSAL_ONLY" if ok else "DISABLED",
        "champion_executed":ok,
        "recommended_departure_timestamp":dep,
        "recommended_arrival_timestamp":arr}
    }


def collector(path,positive=True,known_gap=False):
    with sqlite3.connect(path) as c:
        c.executescript("""
          CREATE TABLE stock_history (
             id INTEGER PRIMARY KEY,
             timestamp INTEGER,country TEXT,item_name TEXT,quantity INTEGER,source TEXT);
          CREATE TABLE poll_heartbeats(
             timestamp INTEGER,mode TEXT,success INTEGER);
          CREATE TABLE collection_gaps(
             start_timestamp INTEGER,end_timestamp INTEGER,reason TEXT);
        """)
        q=70 if positive else 0
        for i,t in enumerate(range(BASE,BASE+60000,30)):
            c.execute("INSERT INTO stock_history VALUES (?,?,?,?,?,?)",
                (i+1,t,"can","Fire Hydrant",q,"synthetic"))
            c.execute("INSERT INTO poll_heartbeats VALUES (?,?,?)",
                (t,"poll-cycle",1))
        if known_gap:
            c.execute("INSERT INTO collection_gaps VALUES (?,?,?)",
                      (BASE+920,BASE+1020,"test"))


class ShadowOutcomeTests(unittest.TestCase):
    def test_positive_negative_gap_and_unresolved(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/"stock.db";collector(db)
            con=sqlite3.connect(db)
            a=arrival_truth(con,"can","Fire Hydrant",BASE+1000,BASE+30000)
            self.assertEqual(a["status"],"RESOLVED_SUCCESS")
            self.assertIs(arrival_truth(con,"can","Fire Hydrant",BASE+1000,BASE+1005)["success"],None)
            con.execute("UPDATE stock_history SET quantity=0 WHERE timestamp BETWEEN ? AND ?",
                        (BASE+900,BASE+1100))
            con.commit()
            self.assertEqual(arrival_truth(con,"can","Fire Hydrant",BASE+1000,BASE+30000)["status"],"RESOLVED_MISS")
            con.execute("UPDATE stock_history SET quantity=100 WHERE timestamp=?",(BASE+1020,))
            con.commit()
            self.assertEqual(arrival_truth(con,"can","Fire Hydrant",BASE+1000,BASE+30000)["status"],"UNSCORABLE_TRANSITION_NEAR_ARRIVAL")
            con.execute("INSERT INTO collection_gaps VALUES (?,?,?)",(BASE+990,BASE+1010,"test"))
            con.commit()
            self.assertEqual(arrival_truth(con,"can","Fire Hydrant",BASE+1000,BASE+30000)["status"],"UNSCORABLE_KNOWN_GAP")
            con.close()

    def test_read_only_frozen_pre_capture_and_missing_recommendations(self):
        with tempfile.TemporaryDirectory() as td:
            raw=Path(td)/"stock.db";collector(raw)
            ledger=Path(td)/"evidence.db"
            record_private_decision(ledger,snapshot(BASE+100,BASE+120,BASE+1000),"newpilot",now=BASE+101)
            record_private_decision(ledger,snapshot(BASE+500),"newpilot",now=BASE+502)
            record_private_decision(ledger,snapshot(BASE+800,BASE+820,BASE+1020),"oldpilot",now=BASE+801)
            before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in [raw,ledger]]
            report=score_capture(ledger,raw,experiment="newpilot",
                    freeze_epoch=BASE,asof_epoch=BASE+56000)
            self.assertEqual(report["items"]["can:Fire Hydrant"]["captured"],2)
            self.assertEqual(report["items"]["can:Fire Hydrant"]["resolved_eligible_sessions"],2)
            self.assertEqual(report["items"]["can:Fire Hydrant"]["successful_arrivals"],1)
            self.assertEqual(report["items"]["can:Fire Hydrant"]["all_start_success"],.5)
            self.assertEqual(report["items"]["can:Fire Hydrant"]["coverage"],.5)
            self.assertFalse(report["items"]["can:Fire Hydrant"]["independent_window_certified"])
            after=[hashlib.sha256(p.read_bytes()).hexdigest() for p in [raw,ledger]]
            self.assertEqual(before,after)

    def test_pre_freeze_decisions_not_allowed_into_forward_test(self):
        with tempfile.TemporaryDirectory() as td:
            raw=Path(td)/"stock.db";collector(raw)
            ledger=Path(td)/"evidence.db"
            record_private_decision(ledger,snapshot(BASE+100,BASE+120,BASE+1000),"newpilot",now=BASE+101)
            report=score_capture(ledger,raw,experiment="newpilot",
                   freeze_epoch=BASE+200,asof_epoch=BASE+56000)
            item=report["items"]["can:Fire Hydrant"]
            self.assertEqual(item["resolved_eligible_sessions"],0)
            self.assertEqual(item["rows"][0]["status"],"EXCLUDED_PRE_FREEZE_OR_INVALID_CAPTURE")

    def test_pending_horizon_kept_out_of_denominator(self):
        with tempfile.TemporaryDirectory() as td:
            raw=Path(td)/"stock.db";collector(raw)
            ledger=Path(td)/"evidence.db"
            record_private_decision(ledger,snapshot(BASE+100,BASE+120,BASE+1000),"newpilot",now=BASE+101)
            report=score_capture(ledger,raw,experiment="newpilot",
                   freeze_epoch=BASE,asof_epoch=BASE+2000)
            self.assertEqual(report["items"]["can:Fire Hydrant"]["resolved_eligible_sessions"],0)
            self.assertEqual(report["items"]["can:Fire Hydrant"]["rows"][0]["status"],"PENDING_SESSION_HORIZON")


if __name__=="__main__":
    unittest.main()
