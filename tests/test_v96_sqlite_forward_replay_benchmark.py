"""V96 realistic-bounded SQLite replay benchmark for change-only stock history.

1,000 immutable issued recommendations + 3,000 poll-heartbeat cycles. Each
item has long stable stock, which V76's nearest-change scoring would have
omitted. Measures V88 proxy reconstruction speed on GitHub runner only.
No collector, remote VM, YATA, or user accounts are touched.
"""
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from research import v88_poll_state_forward_report as forward
from research.v38_prediction_store import open_writer

NOW=1791650000
ITEMS=("mex:Jaguar Plushie","mex:Dahlia","mex:Fixture Plushie",
       "mex:Fixture Flower")
ISSUE_START=NOW-22*3600


class IndexedSqlReplayTests(unittest.TestCase):
    def test_thousand_decisions_from_unchanged_stock(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        evidence=root/"issued.db"
        stock=root/"collector.db"

        with open_writer(evidence) as db:
            issued=[]
            for item in ITEMS:
                for i in range(250):
                    at=ISSUE_START+i*300
                    depart=at+600
                    issued.append((item,at,"fixture","stability",at-20,
                                   "RESEARCH_PROPOSAL_ONLY",depart,
                                   depart+1020,at+300,0))
            db.executemany("""INSERT INTO v42_candidate_decisions
                (item_key,computed_at,model_family,model_config,stock_as_of,
                 status,departure,arrival,valid_until,actual_player_departure)
                 VALUES(?,?,?,?,?,?,?,?,?,?)""",issued)

        with sqlite3.connect(stock) as db:
            db.executescript("""
                CREATE TABLE stock_history(
                    id INTEGER PRIMARY KEY,timestamp INTEGER,
                    country TEXT,item_name TEXT,quantity INTEGER,source TEXT);
                CREATE INDEX idx_country_item_lookup
                    ON stock_history(country,item_name,timestamp);
                CREATE TABLE poll_heartbeats(
                    id INTEGER PRIMARY KEY,timestamp INTEGER,
                    mode TEXT, success INTEGER,source TEXT);
                CREATE INDEX idx_heartbeats ON poll_heartbeats(timestamp);
                CREATE TABLE collection_gaps(
                    start_timestamp INTEGER,end_timestamp INTEGER);
            """)
            db.executemany("""INSERT INTO stock_history(
                timestamp,country,item_name,quantity,source)
                VALUES(?,'mex',?,85,'yata')""",
                [(ISSUE_START-100,item.split(":",1)[1]) for item in ITEMS])
            polls=[(ts,"poll-cycle",1,"yata")
                   for ts in range(ISSUE_START-120,NOW+31,30)]
            db.executemany("""INSERT INTO poll_heartbeats(
                timestamp,mode,success,source) VALUES(?,?,?,?)""",polls)

        start=time.perf_counter()
        output=forward.report(
            ledger=evidence,stock=stock,now=NOW,days=1,limit=1200)
        elapsed=time.perf_counter()-start
        print("V96_INDEXED_SQLITE_AUDIT_BENCHMARK",
              round(elapsed,3),"seconds",
              output["unique_item_arrival_targets"],"arrival targets",
              len(polls),"poll heartbeats",flush=True)
        self.assertLess(elapsed,20,
                        "Bounded audit too costly even on CI machine")
        self.assertEqual(output["unique_item_arrival_targets"],1000)
        self.assertEqual(output["proxy_scorable"],1000)
        self.assertEqual(output["proxy_success"],1000)
        self.assertEqual(output["matched_immediate_departure_baseline"]["count"],1000)
        self.assertEqual(output["direct_stock_change_samples"][
            "NO_SAMPLE_WITHIN_10_SECONDS"],1000)
        self.assertFalse(output["exact_10s_accuracy_certified"])
        self.assertFalse(output["per_country_YATA_snapshot_freshness_certified"])


if __name__=="__main__":
    unittest.main()
