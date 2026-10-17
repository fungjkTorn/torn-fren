"""V98: preserve full issue cohort and never call six-hour WATCH an actionable flight."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research import v98_ready_vs_watch_forward_audit as m
from research.v38_prediction_store import open_writer
from research.plushie_champions.common import TRAVEL_SECONDS

NOW=1791650000
ISSUE=NOW-7200
FLIGHT=TRAVEL_SECONDS["mex"]


class ReadyVsWatchTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        self.ledger=root/"candidates.db"
        self.stock=root/"stock.db"
        with open_writer(self.ledger) as con:
            self._insert(con, "mex:Jaguar Plushie", ISSUE, 120)
            self._insert(con, "mex:Dahlia", ISSUE, 3600)
            # Duplicate same item+arrival at different as-issued times.
            self._insert(con, "mex:Jaguar Plushie", ISSUE+30, 90)
            self._insert(con, "mex:Dahlia", ISSUE+30, 3570)
            # Explicit abstention is not a flight.
            self._insert(con,"mex:Jaguar Plushie", ISSUE+300, None)

        with sqlite3.connect(self.stock) as db:
            db.executescript("""
              CREATE TABLE stock_history(
                id INTEGER PRIMARY KEY,timestamp INTEGER,country TEXT,
                item_name TEXT,quantity INTEGER,source TEXT);
              CREATE INDEX idx_stock ON stock_history(country,item_name,timestamp);
              CREATE TABLE poll_heartbeats(
                id INTEGER PRIMARY KEY,timestamp INTEGER,mode TEXT,
                success INTEGER,source TEXT);
              CREATE INDEX idx_poll ON poll_heartbeats(timestamp);
              CREATE TABLE collection_gaps(
                start_timestamp INTEGER,end_timestamp INTEGER);
            """)
            db.executemany(
                "INSERT INTO stock_history(timestamp,country,item_name,quantity,source) "
                "VALUES(?,'mex',?,?,'yata')",
                [(ISSUE-300,"Jaguar Plushie",100),
                 (ISSUE-300,"Dahlia",0)])
            db.executemany(
                "INSERT INTO poll_heartbeats(timestamp,mode,success,source) "
                "VALUES(?,'poll-cycle',1,'yata')",
                [(x,) for x in range(ISSUE-300,NOW+40,30)])

    def _insert(self, db, key, issued, wait):
        dep=None if wait is None else issued+wait
        arr=None if dep is None else dep+FLIGHT
        state="EXPERT_ABSTAINED" if dep is None else "RESEARCH_PROPOSAL_ONLY"
        db.execute("""INSERT INTO v42_candidate_decisions
                     (item_key,computed_at,model_family,model_config,
                      stock_as_of,status,departure,arrival,valid_until,
                      actual_player_departure)
                     VALUES(?,?,?,?,?,?,?,?,?,0)""",
                   (key,issued,"fixture","fixture",issued-20,
                    state,dep,arr,issued+300))
        db.commit()

    def run_audit(self, now=NOW):
        return m.audit(ledger=self.ledger,source=self.stock,now=now,days=1)

    def test_ready_and_watch_are_different_denominators(self):
        r=self.run_audit()
        self.assertEqual(r["raw_as_issued_rows"],5)
        self.assertEqual(r["invalid_or_abstained_issued_rows"],1)
        self.assertEqual(r["distinct_item_arrival_targets"],2)
        self.assertEqual(r["duplicate_item_arrival_issue_rows"],2)
        ready=r["partitions"]["ISSUED_READY_WITHIN_5M"]
        watch=r["partitions"]["FUTURE_WATCH_GT_5M"]
        self.assertEqual(ready["arrival_targets"],1)
        self.assertEqual(watch["arrival_targets"],1)
        self.assertEqual(ready["proxy_success"],1)
        self.assertEqual(watch["proxy_miss"],1)
        self.assertEqual(ready["proxy_success_fraction"],1.0)
        self.assertEqual(watch["proxy_success_fraction"],0.0)
        self.assertFalse(r["exact_10s_accuracy_certified"])
        self.assertEqual(r["unique_independent_stock_windows"],None)

    def test_future_watch_arrival_ahead_remains_pending(self):
        r=self.run_audit(now=ISSUE+1200)
        watch=r["partitions"]["FUTURE_WATCH_GT_5M"]
        self.assertEqual(watch["outcomes"]["PENDING"],1)
        self.assertEqual(watch["maturation_stage"][
                         "WAITING_FOR_DEPARTURE"],1)

    def test_missing_collector_has_no_side_effect(self):
        missing=self.stock.parent/"doesnotexist.db"
        with self.assertRaises((OSError,ValueError)):
            m.audit(ledger=self.ledger,source=missing,now=NOW)
        self.assertFalse(missing.exists())

    def test_overlarge_count_fails_without_truncation(self):
        with self.assertRaises(ValueError):
            m.audit(ledger=self.ledger,source=self.stock,now=NOW,max_targets=1)

    def test_unchanged_stock_scored_without_near_arrival_change_row(self):
        r=self.run_audit()
        good=r["partitions"]["ISSUED_READY_WITHIN_5M"]
        self.assertEqual(good["proxy_success"],1)
        self.assertEqual(good["change_only_samples_within_plus_10s"]
                         ["NO_SAMPLE_WITHIN_10_SECONDS"],1)

    def test_not_counting_a_watch_as_actionable_by_status(self):
        r=self.run_audit()
        watch=r["partitions"]["FUTURE_WATCH_GT_5M"]
        self.assertEqual(watch["per_item"]["mex:Dahlia"][
                         "arrival_targets"],1)
        self.assertEqual(watch["maturation_stage"][
                         "MATURED_FOR_OUTCOME_AUDIT"],1)
        self.assertIn("six-hour-later",r["warning"])


if __name__=="__main__":
    unittest.main()
