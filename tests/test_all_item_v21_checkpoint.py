"""Tests for all-item V21 scoring/selection building blocks."""
import json
import tempfile
import unittest
from pathlib import Path

from services.all_item_v21_checkpoint import (
    _atomic, _head_to_head, _immediate_baseline, _sparse_starts,
)


class AllItemCheckpointTests(unittest.TestCase):
    def test_paired_counts_and_outcomes(self):
        old = {
            t: {"success": t % 2 == 0, "wait_seconds": 18000.0}
            for t in range(40)
        }
        new = {
            t: {"success": True, "wait_seconds": 3000.0}
            for t in range(40)
        }
        m = _head_to_head(old, new)
        self.assertTrue(m["eligible"])
        self.assertEqual(m["matched"], 40)
        self.assertEqual(m["v19_hits"], 20)
        self.assertEqual(m["v21_hits"], 40)
        self.assertEqual(m["v21_only_successes"], 20)
        self.assertEqual(m["v19_only_successes"], 0)

    def test_low_overlap_disallows_promotion(self):
        old = {t: {"success": False, "wait_seconds": 0} for t in range(12)}
        new = {t: {"success": True, "wait_seconds": 1000} for t in range(12)}
        x = _head_to_head(old, new)
        self.assertEqual(x["matched"], 12)
        self.assertFalse(x["eligible"])

    def test_depart_now_is_measured_on_actual_stock(self):
        # On a change-only timeline, quantity stays 80 from t=100 to t=600.
        times, qtys = [0,100,600,1000], [0,80,0,0]
        x = _immediate_baseline(times, qtys, [], travel=100, min_qty=30,
                                 grace=10, starts=[0,100,400,600])
        self.assertEqual(x["sessions"], 3)
        self.assertEqual(x["successes"], 2)
        self.assertAlmostEqual(x["rate"], 2/3)

    def test_sparse_holdout_is_chronological_and_bounded(self):
        starts = _sparse_starts([0, 20*86400], 1800)
        self.assertGreater(len(starts), 40)
        self.assertLessEqual(len(starts), 250)
        self.assertEqual(starts, sorted(set(starts)))

    def test_atomic_checkpoint_is_readable(self):
        with tempfile.TemporaryDirectory() as td:
            dst = Path(td) / "results.json"
            _atomic(dst, {"results": {"chi:Peony": {"status": "complete"}}})
            self.assertEqual(json.loads(dst.read_text())["results"]["chi:Peony"]["status"], "complete")
            self.assertFalse((Path(td) / "results.json.writing").exists())


if __name__ == "__main__":
    unittest.main()
