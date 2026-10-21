"""V65 staged research-only mirror conversion and rollback overlay contracts."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from research import v65_private_mirror_shadow_tick as v65
from research.v60_private_snapshot_probe import snapshot_once

NOW=1791540000
CONF=Path(__file__).resolve().parents[1]/"deploy"/"systemd"/"v65-private-mirror19.conf"


def source_with_heartbeat(path):
    with sqlite3.connect(path) as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("""CREATE TABLE stock_history(
            id INTEGER PRIMARY KEY,timestamp INTEGER,
            country TEXT,item_name TEXT,quantity INTEGER,source TEXT)""")
        c.execute("""CREATE TABLE poll_heartbeats(
            timestamp INTEGER,mode TEXT,success INTEGER)""")
        c.execute("""CREATE TABLE collection_gaps(
            id INTEGER PRIMARY KEY,start_timestamp INTEGER,end_timestamp INTEGER,reason TEXT)""")
        c.execute("INSERT INTO stock_history VALUES(1,?,?,?,?,?)",
                  (NOW-30,"uni","Heather",40,"test"))
        c.execute("INSERT INTO poll_heartbeats VALUES(?,'poll-cycle',1)",
                  (NOW-15,))


class V65MirrorShadowTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        root=Path(t.name)
        self.source=root/"source"/"stock.db"
        self.source.parent.mkdir()
        source_with_heartbeat(self.source)
        self.snapshot=root/"private"/"snapshot.db"
        self.sidecar=root/"private"/"predictions.db"

    def backup(self,source,dest):
        return snapshot_once(source,dest,now_fn=lambda:NOW)

    def test_exact_19_uses_original_due_cadence_without_forcing_active(self):
        roster=v65.exact_roster()
        infer=Mock(return_value={"mode":"EXECUTED_RESEARCH_ONLY",
             "executed":[{"item_key":k,"status":"RESEARCH_PROPOSAL_ONLY"}
                         for k in roster]})
        before=self.source.read_bytes()
        result=v65.tick(source=self.source,snapshot=self.snapshot,
           sidecar=self.sidecar,snapshotter=self.backup,infer=infer,
           capacity_probe=lambda:{"allowed":True},clock=lambda:NOW)
        self.assertEqual(result["status"],"V65_EXECUTED_RESEARCH_ONLY")
        self.assertEqual(result["proposal_count"],19)
        self.assertEqual(result["error_count"],0)
        self.assertEqual(result["end_heartbeat_age_seconds"],15)
        self.assertEqual(self.source.read_bytes(),before)
        self.assertEqual(infer.call_args.kwargs["stock_db"],self.snapshot)
        self.assertEqual(infer.call_args.kwargs["sidecar_db"],self.sidecar)
        self.assertEqual(set(infer.call_args.kwargs["approved_keys"]),set(roster))
        self.assertNotIn("active",infer.call_args.kwargs)
        self.assertTrue(infer.call_args.kwargs["with_redfox"])
        self.assertTrue(infer.call_args.kwargs["with_xanax"])
        self.assertEqual(infer.call_args.kwargs["max_jobs"],19)
        self.assertEqual(infer.call_args.kwargs["budget_seconds"],220)

    def test_stale_collector_does_not_touch_active_sidecar_or_run_inference(self):
        infer=Mock()
        snapshotter=Mock(return_value={"status":"SOURCE_HEARTBEAT_STALE","published":False})
        result=v65.tick(source=self.source,snapshot=self.snapshot,
             sidecar=self.sidecar,snapshotter=snapshotter,infer=infer,
             capacity_probe=lambda:{"allowed":True})
        self.assertEqual(result["status"],"V65_NO_FRESH_SNAPSHOT")
        infer.assert_not_called()
        self.assertFalse(self.sidecar.exists())

    def test_pressure_gate_runs_before_any_snapshot(self):
        snapshotter=Mock()
        runner=Mock()
        out=v65.tick(source=self.source,snapshot=self.snapshot,
                     sidecar=self.sidecar,snapshotter=snapshotter,infer=runner,
                     capacity_probe=lambda:{"allowed":False})
        self.assertEqual(out["status"],"V65_DEFERRED_CPU_PRESSURE")
        snapshotter.assert_not_called()
        runner.assert_not_called()

    def test_snapshot_transient_readonly_recovery_retries_but_not_unrelated(self):
        calls=[]
        def flaky(*a):
            calls.append(1)
            if len(calls)<3:
                exc=sqlite3.OperationalError("never print raw text")
                exc.sqlite_errorcode=264
                raise exc
            return {"status":"PRIVATE_SNAPSHOT_READY","published":True}
        delays=[]
        out=v65.snapshot_with_retry(self.source,self.snapshot,
              snapshotter=flaky,sleep=delays.append,delays=(.25,.75))
        self.assertTrue(out["published"])
        self.assertEqual(len(calls),3)
        self.assertEqual(delays,[.25,.75])
        nope=[]
        def unrelated(*a):
            nope.append(1)
            exc=sqlite3.OperationalError("no such table: abc")
            exc.sqlite_errorcode=sqlite3.SQLITE_ERROR
            raise exc
        with self.assertRaises(sqlite3.OperationalError):
            v65.snapshot_with_retry(self.source,self.snapshot,
                                   snapshotter=unrelated,sleep=lambda _:None)
        self.assertEqual(len(nope),1)

    def test_snapshot_permanent_failure_is_private_and_does_not_reuse_old_db(self):
        exc=sqlite3.OperationalError("private DB path is secret")
        exc.sqlite_errorcode=14
        calls=[]
        def fail(*args):
            calls.append(1)
            raise exc
        with patch("research.v65_private_mirror_shadow_tick.time.sleep"):
            result=v65.tick(source=self.source,snapshot=self.snapshot,
                 sidecar=self.sidecar,
                 snapshotter=lambda a,b:v65.snapshot_with_retry(a,b,snapshotter=fail,
                                                                sleep=lambda _:None),
                 infer=Mock(),capacity_probe=lambda:{"allowed":True})
        self.assertEqual(result["status"],"V65_SNAPSHOT_ERROR")
        self.assertEqual(result["error_tag"],"SQLITE_CANTOPEN")
        self.assertEqual(result["sqlite_extended_code"],14)
        self.assertEqual(len(calls),3)
        self.assertNotIn("private DB",json.dumps(result))
        self.assertFalse(self.sidecar.exists())

    def test_runner_failures_and_abstentions_are_not_hidden(self):
        results=[{"item_key":"uni:Heather","status":"V38_NATIVE_ERROR"},
                 {"item_key":"chi:Peony","status":"COLLECTOR_STALE_OR_NO_HEARTBEAT"}]
        out=v65.tick(source=self.source,snapshot=self.snapshot,
            sidecar=self.sidecar,snapshotter=self.backup,
            infer=lambda **kw:{"mode":"EXECUTED_RESEARCH_ONLY","executed":results},
            capacity_probe=lambda:{"allowed":True},clock=lambda:NOW)
        self.assertEqual(out["error_count"],1)
        self.assertEqual(out["stale_count"],1)
        self.assertEqual(out["executed_count"],2)

    def test_scheduled_overlay_changes_only_private_execstart(self):
        raw=CONF.read_text()
        units=[line for line in raw.splitlines() if line.startswith("ExecStart")]
        self.assertEqual(units,[
            "ExecStart=",
            "ExecStart=/home/ubuntu/torn-fren-v38-probe/.venv/bin/python -m research.v65_private_mirror_shadow_tick",
        ])
        self.assertNotIn("ReadWritePaths=",raw)
        self.assertNotIn("CPUQuota=",raw)
        self.assertNotIn("Environment=",raw)
        self.assertNotIn("torn-fren-poller.service",raw)
        self.assertNotIn("torn-fren-v48-cache-warmup.timer",raw)

    def test_live_preflight_rejects_output_symlinks(self):
        with patch.object(v65,"SOURCE",self.source),patch.object(v65,"ROOT",self.snapshot.parent):
            self.snapshot.parent.mkdir(parents=True,exist_ok=True)
            alias=self.snapshot.parent/"v65_stock_snapshot.db"
            alias.symlink_to(self.source)
            with patch.object(v65,"SNAPSHOT",alias),patch.object(v65,"SIDECAR",self.sidecar),patch.object(
                v65,"approved_collector_source",return_value=True):
                with self.assertRaisesRegex(ValueError,"symlink"):
                    v65.preflight()


if __name__=="__main__":
    unittest.main()
