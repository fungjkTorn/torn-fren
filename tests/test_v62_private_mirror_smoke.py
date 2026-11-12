"""V62 separate sidecar + four original specialist routes from one frozen mirror."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from research.v62_private_mirror_smoke import (
    smoke, PROBE_KEYS, LIVE_SIDECAR,
)
from research.v60_private_snapshot_probe import snapshot_once

NOW = 1791540000


def synthetic_source(path):
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("""CREATE TABLE stock_history(
            id INTEGER PRIMARY KEY, timestamp INTEGER, country TEXT,
            item_name TEXT, quantity INTEGER, source TEXT)""")
        db.execute("""CREATE TABLE poll_heartbeats(
            timestamp INTEGER, mode TEXT, success INTEGER)""")
        db.execute("""CREATE TABLE collection_gaps(
            id INTEGER PRIMARY KEY, start_timestamp INTEGER, end_timestamp INTEGER,
            reason TEXT)""")
        db.execute("INSERT INTO poll_heartbeats VALUES(?,'poll-cycle',1)",(NOW-15,))
        db.execute("""INSERT INTO stock_history VALUES
                   (1, ?, 'uni', 'Heather', 40, 'synthetic')""",(NOW-30,))


class V62MirrorSmokeTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.source=self.root/"source"/"stock.db"
        self.source.parent.mkdir()
        synthetic_source(self.source)
        self.mirror=self.root/"research"/"mirror.db"
        self.sidecar=self.root/"research"/"smoke.db"

    def test_one_mirror_and_separate_sidecar_with_source_pinned_routes(self):
        snap_calls=[]
        infer=Mock(return_value={"mode":"EXECUTED_RESEARCH_ONLY",
            "executed":[{"item_key":"uni:Heather","status":"RESEARCH_PROPOSAL_ONLY"},
                        {"item_key":"sou:African Violet","status":"V38_NATIVE_ERROR"}]})
        def back_up(source,dst):
            snap_calls.append((source,dst))
            return snapshot_once(source,dst,now_fn=lambda:NOW)
        before=self.source.read_bytes()
        output=smoke(source=self.source,snapshot=self.mirror,
                     sidecar=self.sidecar,snapshotter=back_up,infer=infer)
        self.assertEqual(output["status"],"V62_SMOKE_EXECUTED")
        self.assertEqual(output["proposal_count"],1)
        self.assertEqual(output["error_count"],1)
        self.assertEqual(len(snap_calls),1)
        self.assertEqual(self.source.read_bytes(),before)
        self.assertFalse(self.sidecar.exists())
        kw=infer.call_args.kwargs
        self.assertEqual(kw["stock_db"],self.mirror)
        self.assertEqual(kw["sidecar_db"],self.sidecar)
        self.assertEqual(kw["approved_keys"],PROBE_KEYS)
        self.assertTrue(kw["with_redfox"])
        self.assertTrue(kw["with_xanax"])
        self.assertEqual(kw["max_jobs"],4)
        self.assertEqual(kw["worker_seconds"],30)
        self.assertTrue(kw["execute"])
        with sqlite3.connect(f"file:{self.mirror}?mode=ro",uri=True) as con:
            self.assertEqual(con.execute("PRAGMA journal_mode").fetchone(),("delete",))

    def test_unavailable_snapshot_never_runs_any_worker(self):
        infer=Mock()
        result=smoke(source=self.source,snapshot=self.mirror,
            sidecar=self.sidecar,infer=infer,
            snapshotter=lambda *a: {"status":"SOURCE_HEARTBEAT_STALE","published":False})
        self.assertEqual(result["status"],"V62_NO_FRESH_SNAPSHOT")
        infer.assert_not_called()
        self.assertFalse(self.sidecar.exists())

    def test_sidecar_equal_to_active_sidecar_is_rejected(self):
        infer=Mock()
        with self.assertRaises(ValueError):
            smoke(source=self.source,snapshot=self.mirror,
                  sidecar=LIVE_SIDECAR,infer=infer)
        infer.assert_not_called()

    def test_sidecar_equal_to_production_db_is_rejected(self):
        with self.assertRaises(ValueError):
            smoke(source=self.source,snapshot=self.mirror,sidecar=self.source)

    def test_snapshot_equal_to_production_db_is_rejected(self):
        with self.assertRaises(ValueError):
            smoke(source=self.source,snapshot=self.source,sidecar=self.sidecar)

    def test_deferred_cpu_uses_normal_capacity_gate_not_force(self):
        def back_up(a,b):
            return snapshot_once(a,b,now_fn=lambda:NOW)
        infer=Mock(return_value={"mode":"DEFERRED_CPU_PRESSURE","executed":[]})
        out=smoke(source=self.source,snapshot=self.mirror,
                  sidecar=self.sidecar,snapshotter=back_up,infer=infer)
        self.assertEqual(out["status"],"V62_SMOKE_DEFERRED")
        self.assertEqual(out["results"],[])
        self.assertEqual(out["proposal_count"],0)

    def test_source_snapshot_stays_fixed_as_collector_advances(self):
        def back_up(a,b):
            return snapshot_once(a,b,now_fn=lambda:NOW)
        def check_infer(**kw):
            with sqlite3.connect(self.source) as collector:
                collector.execute("INSERT INTO stock_history VALUES(2,?,'uni','Heather',0,'synthetic')",(NOW+1,))
            with sqlite3.connect(f"file:{self.mirror}?mode=ro",uri=True) as snapshot:
                self.assertEqual(snapshot.execute("SELECT MAX(id) FROM stock_history").fetchone()[0],1)
            return {"mode":"EXECUTED_RESEARCH_ONLY","executed":[]}
        result=smoke(source=self.source,snapshot=self.mirror,
                     sidecar=self.sidecar,snapshotter=back_up,infer=check_infer)
        self.assertEqual(result["status"],"V62_SMOKE_EXECUTED")


if __name__ == "__main__":
    unittest.main()
