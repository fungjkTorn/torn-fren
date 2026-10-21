"""V99 causality regression: read issue-time stock, never look ahead."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research import v99_issued_stock_vs_forecast_audit as m
from research.v38_prediction_store import open_writer

NOW=1791650000
ISSUE=NOW-4800


class HistoricalIssuedStockTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        self.side=root/"private.db"
        self.stock=root/"stock.db"
        with open_writer(self.side) as c:
            for key,wait in (
                ("mex:Jaguar Plushie",120),
                ("mex:Dahlia",2400),
                ("mex:Near Restock Plushie",120)):
                dep=ISSUE+wait
                c.execute("""INSERT INTO v42_candidate_decisions(
                    item_key,computed_at,model_family,model_config,stock_as_of,
                    status,departure,arrival,valid_until,actual_player_departure)
                    VALUES(?,?,'fixture','fixture',?,
                           'RESEARCH_PROPOSAL_ONLY',?,?,?,0)""",
                    (key,ISSUE,ISSUE-30,dep,dep+1020,ISSUE+300))
            c.commit()
        with sqlite3.connect(self.stock) as c:
            c.executescript("""
                CREATE TABLE stock_history(
                    id INTEGER PRIMARY KEY,timestamp INTEGER,country TEXT,
                    item_name TEXT,quantity INTEGER,source TEXT);
                CREATE INDEX idx ON stock_history(country,item_name,timestamp);
                CREATE TABLE poll_heartbeats(
                    id INTEGER PRIMARY KEY,timestamp INTEGER,source TEXT,
                    mode TEXT,success INTEGER);
                CREATE INDEX idx_hb ON poll_heartbeats(timestamp);
                CREATE TABLE collection_gaps(
                    start_timestamp INTEGER,end_timestamp INTEGER);
            """)
            c.executemany(
                "INSERT INTO stock_history(timestamp,country,item_name,quantity,source) "
                "VALUES(?,'mex',?,?,'yata')",
                [(ISSUE-100,"Jaguar Plushie",125),
                 (ISSUE-100,"Dahlia",0),
                 (ISSUE-100,"Near Restock Plushie",0),
                 (ISSUE+1100,"Near Restock Plushie",60),
                 (ISSUE+3150,"Dahlia",100)])
            c.executemany(
                "INSERT INTO poll_heartbeats(timestamp,source,mode,success) "
                "VALUES(?,'yata','poll-cycle',1)",
                [(t,) for t in range(ISSUE-120,NOW+60,30)])

    def run_audit(self):
        return m.audit(ledger=self.side,source=self.stock,days=1,now=NOW)

    def test_as_issued_stock_cohort_independent_of_later_restock(self):
        r=self.run_audit()
        self.assertEqual(r["distinct_item_arrival_targets"],3)
        self.assertEqual(r["issued_stock_states"]["ALREADY_STOCKED"],1)
        self.assertEqual(r["issued_stock_states"]["BELOW_30_AT_ISSUE"],2)
        already=r["cohorts"]["QUICK_0_TO_5M/ALREADY_STOCKED"]
        self.assertEqual(already["arrival_success"],1)
        self.assertEqual(already["both_success"],1)
        quick_new=r["cohorts"]["QUICK_0_TO_5M/BELOW_30_AT_ISSUE"]
        self.assertEqual(quick_new["recommendation_only"],1)
        self.assertEqual(quick_new["arrival_success"],1)
        late=r["cohorts"]["WATCH_OVER_5M/BELOW_30_AT_ISSUE"]
        self.assertEqual(late["recommendation_only"],1)
        self.assertEqual(late["arrival_success"],1)
        self.assertFalse(r["exact_arrival_accuracy_certified"])
        self.assertFalse(r["independent_restock_events_certified"])

    def test_future_stock_record_cannot_make_issue_appear_already_stocked(self):
        with sqlite3.connect(self.stock) as c:
            c.execute("""UPDATE stock_history SET quantity=0
                         WHERE item_name='Jaguar Plushie'""")
            c.execute("""INSERT INTO stock_history(timestamp,country,item_name,
                         quantity,source)
                         VALUES(?,'mex','Jaguar Plushie',100,'yata')""",
                      (ISSUE+2000,))
        r=self.run_audit()
        self.assertEqual(r["issued_stock_states"]["BELOW_30_AT_ISSUE"],3)
        self.assertNotIn("QUICK_0_TO_5M/ALREADY_STOCKED",r["cohorts"])

    def test_mixed_provider_issuance_is_unknown_not_a_win(self):
        with sqlite3.connect(self.stock) as c:
            c.execute("""UPDATE stock_history SET source='prometheus'
                         WHERE item_name='Jaguar Plushie'""")
        r=self.run_audit()
        self.assertEqual(r["issued_stock_states"]["ISSUE_PROVIDER_MISMATCH"],1)

    def test_read_only_and_separate_databases(self):
        with sqlite3.connect(self.stock) as c:
            before=c.execute("SELECT COUNT(*) FROM stock_history").fetchone()[0]
        self.run_audit()
        with sqlite3.connect(self.stock) as c:
            after=c.execute("SELECT COUNT(*) FROM stock_history").fetchone()[0]
        self.assertEqual(before,after)
        with self.assertRaises(ValueError):
            m.audit(ledger=self.side,source=self.side,days=1,now=NOW)

    def test_unknown_stale_issuance(self):
        with sqlite3.connect(self.stock) as c:
            c.execute("""DELETE FROM stock_history
                         WHERE item_name='Jaguar Plushie'""")
        r=self.run_audit()
        self.assertEqual(r["issued_stock_states"]["NO_ISSUE_STOCK_RECORD"],1)

    def test_empty_or_missing_source_refused(self):
        with self.assertRaises((OSError,ValueError)):
            m.audit(ledger=self.side,source=self.stock.parent/"absent.db",
                    days=1,now=NOW)
        self.assertFalse((self.stock.parent/"absent.db").exists())


if __name__=="__main__":
    unittest.main()
