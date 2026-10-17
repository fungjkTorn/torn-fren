"""V88 regression: no per-item change does not mean no YATA stock evidence."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research.v38_prediction_store import open_writer,record
from research.plushie_champions.common import TRAVEL_SECONDS
from research import v88_poll_state_forward_report as m

NOW=1791650000
ISSUED=NOW-200
ARR=NOW+7800
KEY="arg:Monkey Plushie"
FLIGHT=TRAVEL_SECONDS["arg"]
DEP=ARR-FLIGHT
BASELINE=ISSUED+FLIGHT


class HeartbeatStateTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.stockdb=self.root/"stock.db"
        self.ledger=self.root/"ledger.db"
        with sqlite3.connect(self.stockdb) as c:
            c.execute("""CREATE TABLE stock_history(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER,country TEXT,item_name TEXT,
                quantity INTEGER,source TEXT)""")
            c.execute("""CREATE TABLE poll_heartbeats(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER,mode TEXT,success INTEGER,source TEXT)""")
            c.execute("""CREATE TABLE collection_gaps(
                start_timestamp INTEGER,end_timestamp INTEGER)""")
            for timepoint in (BASELINE,ARR):
                self.heartbeat(c,timepoint-12)
                self.heartbeat(c,timepoint+38)
        con=open_writer(self.ledger)
        record(con,key=KEY,family="offline_fixture",config="fixture",
               output={"status":"RESEARCH_PROPOSAL_ONLY",
                       "recommended_departure_timestamp":DEP,
                       "recommended_arrival_timestamp":ARR,
                       "quantity_threshold":30,"grace_seconds":10,
                       "replan_step_seconds":300,
                       "probability_calibrated":False},
               now=ISSUED,stock_as_of=ISSUED-20,executed=True,
               next_due=ISSUED+300)
        con.close()

    def stock(self,c,ts,qty):
        c.execute("""INSERT INTO stock_history
                (timestamp,country,item_name,quantity,source)
                VALUES(?,'arg','Monkey Plushie',?,'yata')""",(ts,qty))

    def heartbeat(self,c,ts,source="yata"):
        c.execute("""INSERT INTO poll_heartbeats
                  (timestamp,mode,success,source)
                  VALUES(?,'poll-cycle',1,?)""",(ts,source))

    def run_report(self):
        return m.report(ledger=self.ledger,stock=self.stockdb,
                        days=1,now=ARR+300)

    def test_unchanged_available_stock_counts_as_proxy_success(self):
        with sqlite3.connect(self.stockdb) as c:
            self.stock(c,ISSUED-50,100)
        report=self.run_report()
        self.assertEqual(report["unique_item_arrival_targets"],1)
        self.assertEqual(report["proxy_scorable"],1)
        self.assertEqual(report["proxy_success"],1)
        self.assertEqual(report["proxy_miss"],0)
        self.assertEqual(report["matched_immediate_departure_baseline"]["both_success"],1)
        self.assertEqual(report["direct_stock_change_samples"].get(
            "NO_SAMPLE_WITHIN_10_SECONDS"),1)
        self.assertFalse(report["exact_10s_accuracy_certified"])

    def test_baseline_misses_but_target_arrival_is_available(self):
        with sqlite3.connect(self.stockdb) as c:
            self.stock(c,ISSUED-50,0)
            self.stock(c,ARR-80,60)
        report=self.run_report()
        self.assertEqual(report["proxy_success"],1)
        self.assertEqual(report["matched_immediate_departure_baseline"]["recommendation_only"],1)
        self.assertEqual(report["matched_immediate_departure_baseline"]["immediate_departure_successes"],0)

    def test_both_below_threshold_is_proxy_miss(self):
        with sqlite3.connect(self.stockdb) as c:
            self.stock(c,ISSUED-50,0)
        report=self.run_report()
        self.assertEqual(report["proxy_miss"],1)
        self.assertEqual(report["matched_immediate_departure_baseline"]["both_miss"],1)

    def test_change_inside_arrival_interval_is_uncertain(self):
        with sqlite3.connect(self.stockdb) as c:
            self.stock(c,ISSUED-50,0)
            self.stock(c,ARR+20,100)
        report=self.run_report()
        self.assertEqual(report["proxy_scorable"],0)
        self.assertEqual(report["outcomes"]["THRESHOLD_TRANSITION_BRACKET"],1)

    def test_known_gap_is_not_certified_as_success(self):
        with sqlite3.connect(self.stockdb) as c:
            self.stock(c,ISSUED-50,100)
            c.execute("INSERT INTO collection_gaps VALUES (?,?)",(ARR-30,ARR+40))
        report=self.run_report()
        self.assertEqual(report["proxy_scorable"],0)
        self.assertEqual(report["outcomes"]["KNOWN_COLLECTION_GAP"],1)

    def test_provider_change_is_unknown(self):
        with sqlite3.connect(self.stockdb) as c:
            self.stock(c,ISSUED-50,100)
            c.execute("""UPDATE poll_heartbeats SET source='prometheus'
                         WHERE timestamp=?""",(ARR+38,))
        report=self.run_report()
        self.assertEqual(report["proxy_scorable"],0)
        self.assertEqual(report["outcomes"]["PROVIDER_SWITCH"],1)

    def test_old_delta_record_fails_closed_despite_fresh_global_heartbeat(self):
        with sqlite3.connect(self.stockdb) as c:
            self.stock(c,ARR-2*86400,100)
        report=self.run_report()
        self.assertEqual(report["proxy_scorable"],0)
        self.assertEqual(report["outcomes"]["STOCK_STATE_OLDER_THAN_24H"],1)

    def test_provider_mismatch_not_used_as_stock_truth(self):
        with sqlite3.connect(self.stockdb) as c:
            self.stock(c,ISSUED-50,100)
            c.execute("UPDATE stock_history SET source='prometheus'")
        report=self.run_report()
        self.assertEqual(report["proxy_scorable"],0)
        self.assertEqual(report["outcomes"]["STOCK_STATE_PROVIDER_MISMATCH"],1)

    def test_future_arrival_is_pending(self):
        with sqlite3.connect(self.stockdb) as c:
            self.stock(c,ISSUED-50,100)
        with sqlite3.connect(self.stockdb) as c:
            state=m.observation(c,"arg","Monkey Plushie",ARR,ARR+100)
        self.assertEqual(state[0],"PENDING")

    def test_audit_is_read_only(self):
        with sqlite3.connect(self.stockdb) as c:
            self.stock(c,ISSUED-50,100)
            before=c.execute("SELECT COUNT(*) FROM stock_history").fetchone()[0]
        with sqlite3.connect(self.ledger) as c:
            old=c.execute("SELECT COUNT(*) FROM v42_candidate_decisions").fetchone()[0]
        self.run_report()
        with sqlite3.connect(self.stockdb) as c:
            after=c.execute("SELECT COUNT(*) FROM stock_history").fetchone()[0]
        with sqlite3.connect(self.ledger) as c:
            new=c.execute("SELECT COUNT(*) FROM v42_candidate_decisions").fetchone()[0]
        self.assertEqual(before,after)
        self.assertEqual(old,new)


if __name__ == "__main__":
    unittest.main()
