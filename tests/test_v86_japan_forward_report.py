"""Tests for Japan read-only prospective scoring, no real stock access."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research import v86_japan_forward_report as m
from research.v84_japan_forward_canary import SCHEMA

NOW = 1791683894
ARR = NOW + 11288


class JapanV86ReportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.ledger = root / "japan_forward.db"
        self.stock = root / "collector.db"
        with sqlite3.connect(self.ledger) as con:
            con.execute(SCHEMA)
        with sqlite3.connect(self.stock) as con:
            con.execute("""CREATE TABLE stock_history (
                id INTEGER PRIMARY KEY, timestamp INTEGER, country TEXT,
                item_name TEXT, quantity INTEGER)""")

    def add(self, *, slot=None, status="FORWARD_CANDIDATE_ONLY", config="V7_ordinary_regime",
            departure=NOW + 2348, arrival=ARR):
        slot = NOW // 300 * 300 if slot is None else slot
        with sqlite3.connect(self.ledger) as con:
            con.execute("""INSERT INTO japan_forward_decisions
                (slot,queried_at,issued_at,source_heartbeat,status,
                 model_generation,model_config,departure,arrival,
                 quantity_threshold,grace_seconds,actual_player_departure,
                 source_model,experiment)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (slot, NOW-10, NOW, NOW-35, status, "V8_REGIME_CANDIDATE",
                 config, departure if status == "FORWARD_CANDIDATE_ONLY" else None,
                 arrival if status == "FORWARD_CANDIDATE_ONLY" else None,
                 30, 10, 0, "v8_regime_candidate_checkpoint_parity_pending",
                 "v84_japan_private_canary"))

    def test_pending_first_live_candidate(self):
        self.add()
        result = m.report(self.ledger, self.stock, now=NOW+500)
        c = result["totals"]
        self.assertEqual(c["issued_rows"], 1)
        self.assertEqual(c["valid_candidates"], 1)
        self.assertEqual(c["pending"], 1)
        self.assertEqual(c["proxy_scorable"], 0)
        self.assertIsNone(c["proxy_success_fraction"])
        self.assertFalse(result["approved_for_website"])

    def test_abstention_not_scored(self):
        self.add(status="DEPARTURE_PASSED")
        result = m.report(self.ledger, self.stock, now=NOW+500)
        self.assertEqual(result["totals"]["abstentions"], 1)
        self.assertEqual(result["totals"]["unique_arrivals"], 0)

    def test_future_result_remains_proxy(self):
        self.add(config="V8_rolling_ridge_alpha3_regime")
        with (patch.object(m, "strict_samples", return_value="NO_SAMPLE_WITHIN_10_SECONDS"),
              patch.object(m, "arrival_truth", return_value=("SUCCESS", True))):
            result = m.report(self.ledger, self.stock, now=ARR+250)
        c = result["totals"]
        self.assertEqual(c["proxy_success"], 1)
        self.assertEqual(c["proxy_success_fraction"], 1.0)
        self.assertFalse(result["exact_10_second_accuracy_certified"])
        self.assertFalse(result["independent_restock_certified"])
        self.assertEqual(
            result["by_model_config"]["V8_rolling_ridge_alpha3_regime"]["proxy_success"], 1)

    def test_bad_arrival_rejected(self):
        self.add(arrival=ARR-300)
        result = m.report(self.ledger, self.stock, now=ARR+250)
        self.assertEqual(result["totals"]["invalid_candidates"], 1)
        self.assertEqual(result["totals"]["unique_arrivals"], 0)

    def test_ledger_equals_source_rejected(self):
        with self.assertRaises(ValueError):
            m.report(self.ledger, self.ledger, now=NOW+100)

    def test_empty_ledger_has_explicit_zero_counts(self):
        result = m.report(self.ledger, self.stock, now=NOW + 500)
        self.assertEqual(result["totals"]["unique_arrivals"], 0)
        self.assertEqual(result["totals"]["issued_rows"], 0)
        self.assertEqual(result["totals"]["abstentions"], 0)
        self.assertEqual(result["totals"]["proxy_scorable"], 0)
        self.assertIsNone(result["totals"]["proxy_success_fraction"])

    def test_invalid_window_rejected(self):
        with self.assertRaises(ValueError):
            m.report(self.ledger, self.stock, days=0)


if __name__ == "__main__":
    unittest.main()
