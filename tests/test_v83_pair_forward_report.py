"""V83 reporting tests with synthetic pending/duplicate/proxy stock events."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research import v83_pair_forward_report as m
from research.v81_pair_forward_comparison import SCHEMA

ISSUE = 1791679654


class V83PairReportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.ledger = root / "pair.db"
        self.stock = root / "stock.db"
        with sqlite3.connect(self.ledger) as con:
            con.execute(SCHEMA)
        with sqlite3.connect(self.stock) as con:
            con.execute("""CREATE TABLE stock_history(
              id INTEGER PRIMARY KEY, timestamp INTEGER,
              country TEXT, item_name TEXT, quantity INTEGER)""")

    def insert(self, variant="a", issued=ISSUE, dep=None, status="FORWARD_CANDIDATE_ONLY"):
        dep = ISSUE + 600 if dep is None else dep
        with sqlite3.connect(self.ledger) as con:
            con.execute("""INSERT INTO pair_issued_decisions (
                item_key,variant,issued_at,planned_at,stock_as_of,valid_until,
                status,selected_expert,departure,arrival,artifact_sha256,
                min_quantity,grace_seconds,actual_player_departure)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,0)""",
                ("chi:Panda Plushie", variant, issued,
                 issued // 300 * 300, issued - 20, issued + 300,
                 status, "a", dep if status=="FORWARD_CANDIDATE_ONLY" else None,
                 dep + 9600 if status=="FORWARD_CANDIDATE_ONLY" else None,
                 "f"*64,30,10))

    def test_pending_without_pretend_accuracy(self):
        self.insert()
        report = m.audit(self.ledger, self.stock, now=ISSUE+200, days=1)
        row = report["per_item_variant"]["chi:Panda Plushie"]["a"]
        self.assertEqual(row["pending"], 1)
        self.assertEqual(row["proxy_scorable"], 0)
        self.assertIsNone(row["proxy_success_fraction"])
        self.assertFalse(report["accuracy_exact_at_10_seconds"])
        self.assertFalse(report["actual_player_departure_observed"])

    def test_same_arrival_is_one_target_per_variant(self):
        self.insert(variant="a", issued=ISSUE)
        # A later issuance repeats the same valid arrival target.
        self.insert(variant="a", issued=ISSUE+300)
        self.insert(variant="b", issued=ISSUE)
        report = m.audit(self.ledger, self.stock, now=ISSUE+601, days=1)
        row_a = report["per_item_variant"]["chi:Panda Plushie"]["a"]
        self.assertEqual(row_a["raw_issued_rows"], 2)
        self.assertEqual(row_a["duplicate_arrival_target"], 1)
        self.assertEqual(row_a["unique_arrival_targets"], 1)
        self.assertEqual(report["unique_arrival_targets"], 2)

    def test_proxy_success_is_labelled_not_exact(self):
        self.insert()
        with patch.object(m, "arrival_truth", return_value=("SUCCESS", True)), patch.object(
                m, "strict_samples", return_value="NO_SAMPLE_WITHIN_10_SECONDS"):
            report = m.audit(self.ledger, self.stock, now=ISSUE+12000, days=1)
        row = report["per_item_variant"]["chi:Panda Plushie"]["a"]
        self.assertEqual(row["proxy_success"], 1)
        self.assertEqual(row["proxy_scorable"], 1)
        self.assertEqual(row["proxy_success_fraction"], 1.0)
        self.assertEqual(row["strict_NO_SAMPLE_WITHIN_10_SECONDS"], 1)
        self.assertFalse(report["accuracy_exact_at_10_seconds"])

    def test_invalid_temporal_candidate_rejected(self):
        self.insert(dep=ISSUE-300)
        report = m.audit(self.ledger, self.stock, now=ISSUE+200, days=1)
        row = report["per_item_variant"]["chi:Panda Plushie"]["a"]
        self.assertEqual(row["invalid_proposals"], 1)
        self.assertEqual(report["unique_arrival_targets"], 0)

    def test_invalid_days_fails(self):
        with self.assertRaises(ValueError):
            m.audit(self.ledger, self.stock, days=0)


if __name__ == "__main__":
    unittest.main()
