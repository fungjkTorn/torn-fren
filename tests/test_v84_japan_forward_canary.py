"""V84 isolated Japan forward canary tests; no real collector or VM writes."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research import v84_japan_forward_canary as m

NOW = 1791679501


class JapanV84Tests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        root = Path(t.name)
        self.collector = root / "collector.db"
        self.snapshot = root / "snapshot.db"
        self.ledger = root / "ledger.db"
        self.collector.write_bytes(b"pretend collector")
        self.moments = iter([NOW, NOW + 2])
        self.result = None

    def output(self, path, country, item, now):
        return {"status": "RESEARCH_PROPOSAL_ONLY",
                "key": "jap:Xanax",
                "model_generation": "V8_REGIME_CANDIDATE",
                "model_config": "V8_rolling_ridge_alpha3_regime",
                "research_horizon_seconds": 28800,
                "replan_step_seconds": 300,
                "quantity_threshold": 30,
                "grace_seconds": 10,
                "gameplay_automated": False,
                "probability_calibrated": False,
                "query_timestamp": now,
                "recommended_departure_timestamp": now + 600,
                "recommended_arrival_timestamp": now + 600 + 8940}

    def go(self, predictor=None, busy=False, inspector=None):
        def publish(src, dest):
            Path(dest).write_bytes(b"private snapshot")
            return {"status": "PRIVATE_SNAPSHOT_READY", "published": True}
        return m.tick(
            collector=self.collector, snapshot=self.snapshot,
            ledger=self.ledger,
            clock=lambda: next(self.moments),
            source_approver=lambda _: True,
            snapshotter=publish,
            inspector=inspector or (lambda _p, _now: {
                "status": "FRESH",
                "last_successful_heartbeat": NOW - 20}),
            predictor=predictor or self.output,
            busy_check=lambda: busy)

    def test_fresh_first_run_records_one_candidate(self):
        r = self.go()
        self.assertEqual(r["status"], "V84_JAPAN_RESEARCH_RECORDED")
        self.assertEqual(r["model_status"], "FORWARD_CANDIDATE_ONLY")
        self.assertEqual(r["records_written"], 1)
        self.assertFalse(r["published_to_website"])
        with sqlite3.connect(self.ledger) as con:
            rows = con.execute("""SELECT slot,status,departure,arrival,
                actual_player_departure FROM japan_forward_decisions""").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], (NOW // 300 * 300,
                                  "FORWARD_CANDIDATE_ONLY",
                                  NOW + 600, NOW + 600 + 8940, 0))

    def test_abstention_records_null_departure(self):
        r = self.go(predictor=lambda *_: {"status": "DEPARTURE_PASSED"})
        self.assertEqual(r["model_status"], "DEPARTURE_PASSED")
        with sqlite3.connect(self.ledger) as con:
            x = con.execute("SELECT departure,arrival FROM japan_forward_decisions").fetchone()
        self.assertEqual(x, (None, None))

    def test_contract_violation_not_actionable(self):
        def bad(*args):
            x = self.output(*args)
            x["grace_seconds"] = 60
            return x
        r = self.go(predictor=bad)
        self.assertEqual(r["model_status"], "INVALID_V8_CONTRACT")
        with sqlite3.connect(self.ledger) as con:
            x = con.execute("SELECT departure,arrival FROM japan_forward_decisions").fetchone()
        self.assertEqual(x, (None, None))

    def test_busy_defers_without_writes(self):
        r = self.go(busy=True)
        self.assertEqual(r["status"], "V84_DEFERRED_RESEARCH_BUSY")
        self.assertFalse(self.ledger.exists())
        self.assertFalse(self.snapshot.exists())

    def test_stale_source_rejected(self):
        r = self.go(inspector=lambda _p, _t: {
            "status": "COLLECTOR_STALE_OR_NO_HEARTBEAT"})
        self.assertEqual(r["status"], "V84_SOURCE_NOT_FRESH")
        self.assertFalse(self.ledger.exists())

    def test_expired_slot_rejected_even_with_valid_snapshot(self):
        self.moments = iter([NOW, NOW + 300])
        r = self.go()
        self.assertEqual(r["status"], "V84_PLANNING_SLOT_EXPIRED")
        self.assertFalse(self.ledger.exists())

    def test_sidecar_cannot_equal_source(self):
        with self.assertRaises(ValueError):
            m.safe_paths(self.collector, self.snapshot, self.collector)


if __name__ == "__main__":
    unittest.main()
