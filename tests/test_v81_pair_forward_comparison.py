"""V81 isolated forward-comparison ledger tests; never touch production."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from research import v81_pair_forward_comparison as m

NOW = 1791678350
ASOF = NOW - 20


class Context:
    def __init__(self):
        self.grid = [NOW // 300 * 300]
        self.con = SimpleNamespace(close=lambda: None)


class FakePlanner:
    def __init__(self, ctx, country, item, k, global_weight, cutoff):
        self.k = k

    def plan(self, q):
        return (q + self.k * 300, 0.5, 0.4)


class ForwardPairTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.source = root / "snapshot.db"
        self.source.write_bytes(b"test snapshot")
        self.artifacts = root / "artifacts"
        self.artifacts.mkdir()
        self.ledger = root / "v81.db"
        self.inspect = lambda _p, _now: {
            "status": "FRESH", "last_successful_heartbeat": ASOF,
        }

    def tick(self):
        with (patch.object(m, "load_pinned_artifact",
                           side_effect=lambda _p, _d, target:
                           {"target": target, "train_asof": NOW - 86400}),
              patch.object(m, "original_features",
                           side_effect=lambda _ctx, _c, item, *_args:
                           {"item": item}),
              patch.object(m, "choose_from_features",
                           side_effect=lambda model, _f:
                           model["target"] == "panda")):
            return m.tick(source=self.source, artifact_dir=self.artifacts,
                          ledger=self.ledger, clock=lambda: NOW,
                          inspector=self.inspect,
                          context_builder=lambda *_a, **_kw: Context(),
                          planner_cls=FakePlanner, busy_check=lambda: False)

    def test_six_variants_persist_and_idempotent(self):
        result = self.tick()
        self.assertEqual(result["status"], "V81_PRIVATE_PAIR_RECORDED")
        self.assertEqual(result["records_written"], 6)
        with sqlite3.connect(self.ledger) as con:
            rows = con.execute("""SELECT item_key,variant,status,selected_expert,
                        issued_at,stock_as_of,departure,arrival,
                        actual_player_departure FROM pair_issued_decisions""").fetchall()
        self.assertEqual(len(rows), 6)
        self.assertEqual({r[1] for r in rows}, {"a", "b", "selector"})
        self.assertTrue(all(r[2] == "FORWARD_CANDIDATE_ONLY" for r in rows))
        self.assertTrue(all(r[4] == NOW and r[5] == ASOF and r[8] == 0 for r in rows))
        self.assertEqual({r[3] for r in rows
                          if r[0] == "sou:Lion Plushie" and r[1] == "selector"}, {"a"})
        self.assertEqual({r[3] for r in rows
                          if r[0] == "chi:Panda Plushie" and r[1] == "selector"}, {"b"})
        self.tick()
        with sqlite3.connect(self.ledger) as con:
            self.assertEqual(con.execute(
                "SELECT COUNT(*) FROM pair_issued_decisions").fetchone()[0], 6)

    def test_stale_snapshot_rejected_without_write(self):
        self.inspect = lambda _p, _now: {"status": "COLLECTOR_STALE_OR_NO_HEARTBEAT"}
        result = self.tick()
        self.assertEqual(result["status"], "V81_SOURCE_NOT_FRESH")
        self.assertFalse(self.ledger.exists())

    def test_age_out_rejected_without_write(self):
        moments = iter([NOW, NOW + 200])
        with (patch.object(m, "load_pinned_artifact",
                           side_effect=lambda *_a: {"train_asof": NOW - 86400}),
              patch.object(m, "original_features", return_value={"test": 1}),
              patch.object(m, "choose_from_features", return_value=0)):
            result = m.tick(source=self.source, artifact_dir=self.artifacts,
                ledger=self.ledger, clock=lambda: next(moments),
                inspector=self.inspect,
                context_builder=lambda *_a, **_kw: Context(),
                planner_cls=FakePlanner, busy_check=lambda: False)
        self.assertEqual(result["status"], "V81_SOURCE_CHANGED_OR_STALE")
        self.assertFalse(self.ledger.exists())

    def test_v75_busy_deferred(self):
        result = m.tick(source=self.source, artifact_dir=self.artifacts,
                        ledger=self.ledger, busy_check=lambda: True)
        self.assertEqual(result["status"], "V81_DEFERRED_V75_BUSY")
        self.assertFalse(self.ledger.exists())

    def test_past_departures_null(self):
        class Past(FakePlanner):
            def plan(self, q):
                return (q - 300, 0.5, 0.4)
        with (patch.object(m, "load_pinned_artifact",
                           side_effect=lambda *_a: {"train_asof": NOW - 86400}),
              patch.object(m, "original_features", return_value={"test": 1}),
              patch.object(m, "choose_from_features", return_value=0)):
            result = m.tick(source=self.source, artifact_dir=self.artifacts,
                ledger=self.ledger, clock=lambda: NOW, inspector=self.inspect,
                context_builder=lambda *_a, **_kw: Context(),
                planner_cls=Past, busy_check=lambda: False)
        self.assertEqual(result["status"], "V81_PRIVATE_PAIR_RECORDED")
        with sqlite3.connect(self.ledger) as con:
            rows = con.execute(
                "SELECT status,departure,arrival FROM pair_issued_decisions").fetchall()
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(
            s == "DEPARTURE_PASSED" and dep is None and arr is None
            for s, dep, arr in rows
        ))


if __name__ == "__main__":
    unittest.main()
