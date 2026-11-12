"""V76 real-as-issued research audit: never fabricate an exact 10s success rate."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research import v76_forward_research_report as m
from research.v38_prediction_store import open_writer,record
from research.plushie_champions.common import TRAVEL_SECONDS

NOW=1791650000
ARR=NOW+7800
KEY="arg:Monkey Plushie"
ISSUE=NOW-200
HB=ISSUE-20
DEP=ARR-TRAVEL_SECONDS["arg"]


class ForwardAccuracyTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        self.source=root/"stock.db"
        self.side=root/"private.db"
        with sqlite3.connect(self.source) as c:
            c.execute("""CREATE TABLE stock_history(
              id INTEGER PRIMARY KEY,timestamp INTEGER,country TEXT,
              item_name TEXT,quantity INTEGER,source TEXT)""")
            c.execute("CREATE TABLE poll_heartbeats(timestamp INTEGER,mode TEXT,success INTEGER)")
            c.execute("CREATE TABLE collection_gaps(start_timestamp INTEGER,end_timestamp INTEGER)")
            for ts,qty in ((ARR-60,45),(ARR+60,43)):
                self.stock(c,ts,qty)
            for ts in (ARR-60,ARR+60):
                c.execute("INSERT INTO poll_heartbeats VALUES(?,'poll-cycle',1)",(ts,))
        self.issue(KEY,ISSUE,HB,DEP,ARR)

    def stock(self,c,ts,qty):
        c.execute("""INSERT INTO stock_history(timestamp,country,item_name,quantity,source)
                    VALUES(?,'arg','Monkey Plushie',?,'fixture')""",(ts,qty))

    def issue(self,key,at,stock,dep,arr,status="RESEARCH_PROPOSAL_ONLY"):
        c=open_writer(self.side)
        try:
            data={"status":status,
                  "recommended_departure_timestamp":dep,
                  "recommended_arrival_timestamp":arr,
                  "quantity_threshold":30,"grace_seconds":10,
                  "replan_step_seconds":300,"probability_calibrated":False}
            return record(c,key=key,family="online_template_expert",config="historical",
                    output=data,now=at,stock_as_of=stock,executed=True,next_due=at+300)
        finally:
            c.close()

    def audit(self,ts=ARR+190):
        return m.audit(self.side,self.source,now=ts,days=1)

    def test_future_issue_cannot_be_scored(self):
        r=self.audit(NOW)
        self.assertEqual(r["independent_valid_issued_events"],1)
        self.assertEqual(r["pending"],1)
        self.assertEqual(r["proxy_scorable_events"],0)

    def test_bracket_proxy_not_mislabeled_exact_truth(self):
        r=self.audit()
        self.assertEqual(r["proxy_successes"],1)
        self.assertEqual(r["proxy_misses"],0)
        self.assertFalse(r["prediction_accuracy_calibrated"])
        self.assertFalse(r["reported_as_exact_arrival_accuracy"])
        self.assertEqual(r["strict_without_sample"],1)
        self.assertEqual(r["strict_threshold_directly_observed"],0)
        self.assertFalse(r["collector_written"])
        self.assertFalse(r["sidecar_written"])

    def test_direct_threshold_observation_only_when_in_grace_window(self):
        with sqlite3.connect(self.source) as c:
            self.stock(c,ARR+5,35)
        r=self.audit()
        self.assertEqual(r["strict_threshold_directly_observed"],1)
        self.assertEqual(r["proxy_successes"],1)

    def test_repeated_same_arrival_is_single_independent_event(self):
        self.issue(KEY,ISSUE+50,HB+50,DEP,ARR)
        r=self.audit()
        self.assertEqual(r["raw_candidate_rows"],2)
        self.assertEqual(r["independent_valid_issued_events"],1)
        self.assertEqual(r["proxy_successes"],1)

    def test_bad_issue_time_excluded(self):
        self.issue("can:Xanax",ISSUE+2,HB,ISSUE-1,
                   ISSUE-1+TRAVEL_SECONDS["can"])
        r=self.audit()
        self.assertEqual(r["independent_valid_issued_events"],1)
        self.assertEqual(r["invalid_or_abstained_rows_excluded"],1)

    def test_stale_source_excluded(self):
        with sqlite3.connect(self.side) as c:
            c.execute("UPDATE v42_candidate_decisions SET stock_as_of=?",
                      (ISSUE-190,))
        r=self.audit()
        self.assertEqual(r["independent_valid_issued_events"],0)
        self.assertEqual(r["invalid_or_abstained_rows_excluded"],1)

    def test_known_gap_marks_unscorable(self):
        with sqlite3.connect(self.source) as c:
            c.execute("INSERT INTO collection_gaps VALUES(?,?)",
                      (ARR-50,ARR+30))
        r=self.audit()
        self.assertEqual(r["proxy_scorable_events"],0)
        self.assertEqual(r["status_counts"]["UNSCORABLE_KNOWN_COLLECTION_GAP"],1)

    def test_missing_bracketing_samples_not_miss(self):
        with sqlite3.connect(self.source) as c:
            c.execute("DELETE FROM stock_history WHERE timestamp>=?",(ARR,))
        r=self.audit()
        self.assertEqual(r["proxy_misses"],0)
        self.assertEqual(r["status_counts"]["UNSCORABLE_NO_BRACKETING_STOCK"],1)

    def test_missing_or_same_input_rejected(self):
        with self.assertRaises(ValueError):
            m.audit(self.side,self.side,now=ARR+200)
        with self.assertRaises((OSError,ValueError)):
            m.audit(self.side,self.source.parent/"absent.db",now=ARR+200)

    def test_no_mutations_to_candidate_or_collector_data(self):
        with sqlite3.connect(self.side) as c:
            before=c.execute("SELECT COUNT(*),MIN(departure) FROM v42_candidate_decisions").fetchone()
        with sqlite3.connect(self.source) as c:
            stock_before=c.execute("SELECT COUNT(*),SUM(quantity) FROM stock_history").fetchone()
        self.audit()
        with sqlite3.connect(self.side) as c:
            after=c.execute("SELECT COUNT(*),MIN(departure) FROM v42_candidate_decisions").fetchone()
        with sqlite3.connect(self.source) as c:
            stock_after=c.execute("SELECT COUNT(*),SUM(quantity) FROM stock_history").fetchone()
        self.assertEqual(before,after)
        self.assertEqual(stock_before,stock_after)

if __name__=="__main__":
    unittest.main()
