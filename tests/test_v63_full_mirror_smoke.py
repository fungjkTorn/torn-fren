"""V63 guarded 19-current-champion one-shot smoke, never production routing."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from research.v60_private_snapshot_probe import snapshot_once
from research.v63_full_mirror_smoke import (
    exact_roster, smoke, source_age, LIVE_SIDECAR, RED_FOX_KEY,
    WALL_BUDGET, MAX_JOBS,
)
from research.v38_readonly_resource_probe import ALL as PINNED
from research.v42_xanax_candidate_tick import ALLOWED as XANAX

NOW=1791540000


def seed(db):
    with sqlite3.connect(db) as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("""CREATE TABLE stock_history(
          id INTEGER PRIMARY KEY,timestamp INTEGER,country TEXT,
          item_name TEXT,quantity INTEGER,source TEXT)""")
        c.execute("""CREATE TABLE collection_gaps(
          id INTEGER PRIMARY KEY,start_timestamp INTEGER,
          end_timestamp INTEGER,reason TEXT)""")
        c.execute("""CREATE TABLE poll_heartbeats(
          timestamp INTEGER, mode TEXT, success INTEGER)""")
        c.execute("INSERT INTO stock_history VALUES(1,?,?,?,?,?)",
                  (NOW-30,"uni","Heather",40,"synthetic"))
        c.execute("INSERT INTO poll_heartbeats VALUES(?,'poll-cycle',1)",(NOW-15,))


class V63FullMirrorTests(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root=Path(d.name)
        self.source=self.root/"live"/"stock.db"
        self.source.parent.mkdir()
        seed(self.source)
        self.snapshot=self.root/"private"/"mirror.db"
        self.sidecar=self.root/"private"/"full_smoke.db"

    def backup(self,source,destination):
        return snapshot_once(source,destination,now_fn=lambda:NOW)

    def test_exact_original_19_not_provisional_24(self):
        roster=exact_roster()
        self.assertEqual(len(roster),19)
        self.assertEqual(set(roster),set(PINNED)|set(XANAX)|{RED_FOX_KEY})
        self.assertNotIn("arg:Monkey Plushie",roster)
        self.assertNotIn("swi:Chamois Plushie",roster)
        self.assertNotIn("jap:Xanax",roster)

    def test_mock_full_19_route_and_private_sidecar(self):
        roster=exact_roster()
        infer=Mock(return_value={
            "mode":"EXECUTED_RESEARCH_ONLY",
            "executed":[{"item_key":key,"status":"RESEARCH_PROPOSAL_ONLY"}
                        for key in roster],
        })
        before=self.source.read_bytes()
        res=smoke(source=self.source,snapshot=self.snapshot,sidecar=self.sidecar,
                  snapshotter=self.backup,infer=infer,clock=lambda:NOW)
        self.assertEqual(res["status"],"V63_FULL_MIRROR_EXECUTED")
        self.assertEqual(res["proposal_count"],19)
        self.assertEqual(res["executed_count"],19)
        self.assertEqual(res["native_error_count"],0)
        self.assertEqual(res["missing_model_keys"],[])
        self.assertEqual(res["end_heartbeat_age_seconds"],15)
        self.assertEqual(self.source.read_bytes(),before)
        kwargs=infer.call_args.kwargs
        self.assertEqual(kwargs["stock_db"],self.snapshot)
        self.assertEqual(kwargs["sidecar_db"],self.sidecar)
        self.assertEqual(set(kwargs["approved_keys"]),set(roster))
        self.assertEqual(set(kwargs["active"]),set(roster))
        self.assertTrue(kwargs["with_redfox"])
        self.assertTrue(kwargs["with_xanax"])
        self.assertEqual(kwargs["max_jobs"],MAX_JOBS)
        self.assertEqual(kwargs["budget_seconds"],WALL_BUDGET)
        self.assertFalse(self.sidecar.exists())
        with sqlite3.connect(f"file:{self.snapshot}?mode=ro",uri=True) as c:
            self.assertEqual(c.execute("PRAGMA journal_mode").fetchone(),("delete",))
        self.assertNotEqual(self.sidecar,LIVE_SIDECAR)

    def test_stale_snapshot_never_executes_any_model(self):
        infer=Mock()
        res=smoke(source=self.source,snapshot=self.snapshot,sidecar=self.sidecar,
            snapshotter=lambda a,b:{"status":"SOURCE_HEARTBEAT_STALE","published":False},
            infer=infer)
        self.assertEqual(res["status"],"V63_SNAPSHOT_NOT_READY")
        infer.assert_not_called()
        self.assertFalse(self.sidecar.exists())

    def test_failure_and_deferral_are_reported_not_hidden(self):
        keys=exact_roster()
        out=[
          {"item_key":keys[0],"status":"V38_NATIVE_ERROR","error_tag":"SQLITE_CANTOPEN"},
          {"item_key":keys[1],"status":"WORKER_TIMEOUT"},
          {"item_key":keys[2],"status":"COLLECTOR_STALE_OR_NO_HEARTBEAT"},
          {"item_key":keys[3],"status":"DEFERRED_BUDGET"},
        ]
        infer=Mock(return_value={"mode":"EXECUTED_RESEARCH_ONLY","executed":out})
        result=smoke(source=self.source,snapshot=self.snapshot,sidecar=self.sidecar,
                     snapshotter=self.backup,infer=infer,clock=lambda:NOW)
        self.assertEqual(result["native_error_count"],1)
        self.assertEqual(result["timeout_count"],1)
        self.assertEqual(result["stale_count"],1)
        self.assertEqual(result["deferred_budget_count"],1)
        self.assertEqual(result["executed_count"],4)
        self.assertEqual(len(result["missing_model_keys"]),15)

    def test_private_snapshot_heartbeat_ages_and_cannot_claim_live(self):
        self.backup(self.source,self.snapshot)
        self.assertEqual(source_age(self.snapshot,clock=lambda:NOW+60),75)
        self.assertEqual(source_age(self.snapshot,clock=lambda:NOW+250),265)

    def test_deferred_cpu_does_not_misreport_success(self):
        infer=Mock(return_value={"mode":"DEFERRED_CPU_PRESSURE","executed":[]})
        result=smoke(source=self.source,snapshot=self.snapshot,sidecar=self.sidecar,
                     snapshotter=self.backup,infer=infer,clock=lambda:NOW)
        self.assertEqual(result["status"],"V63_FULL_MIRROR_DEFERRED")
        self.assertEqual(result["executed_count"],0)
        self.assertEqual(len(result["missing_model_keys"]),19)

    def test_rejects_active_sidecar_and_production_source_writes(self):
        for invalid_sidecar in (self.source,LIVE_SIDECAR,self.snapshot):
            with self.subTest(invalid=str(invalid_sidecar)):
                with self.assertRaises(ValueError):
                    smoke(source=self.source,snapshot=self.snapshot,
                          sidecar=invalid_sidecar,snapshotter=self.backup)
        with self.assertRaises(ValueError):
            smoke(source=self.source,snapshot=self.source,
                  sidecar=self.sidecar,snapshotter=self.backup)


if __name__=="__main__":
    unittest.main()
