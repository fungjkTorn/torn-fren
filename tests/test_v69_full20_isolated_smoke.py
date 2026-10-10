"""V69 isolated 20-model end-to-end stage; no installed research timer changes."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from research import v69_full20_isolated_smoke as m
from research.v60_private_snapshot_probe import snapshot_once
from research.v38_prediction_store import open_writer,record

NOW=1791650000
HEARTBEAT=NOW-10
OUTPUT={
 "status":"RESEARCH_PROPOSAL_ONLY",
 "recommended_departure_timestamp":NOW+1800,
 "recommended_arrival_timestamp":NOW+8460,
 "quantity_threshold":30,"grace_seconds":10,
 "replan_step_seconds":300,"probability_calibrated":False,
}


class Full20SmokeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        self.source=root/"collector"/"stock.db"
        self.source.parent.mkdir()
        self.snapshot=root/"research"/"mirror.db"
        self.sidecar=root/"research"/"isolated.db"
        self.cache=root/"evidence"/"v48.db"
        self.cache.parent.mkdir()
        self.cache.write_bytes(b"untouched")
        self.original_keys=m.original.exact_roster()
        with sqlite3.connect(self.source) as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("""CREATE TABLE stock_history(
                id INTEGER PRIMARY KEY,timestamp INTEGER,country TEXT,
                item_name TEXT,quantity INTEGER,source TEXT)""")
            con.execute("CREATE TABLE poll_heartbeats(timestamp INTEGER,mode TEXT,success INTEGER)")
            con.execute("CREATE TABLE collection_gaps(start_timestamp INTEGER,end_timestamp INTEGER)")
            con.execute("INSERT INTO stock_history VALUES(1,?,?,?,?,?)",
                       (NOW-500,"arg","Monkey Plushie",33,"test"))
            con.execute("INSERT INTO poll_heartbeats VALUES(?,'poll-cycle',1)",(HEARTBEAT,))
        self.calls=[]
        self.inject_no_monkey=False
        self.inject_baseline_missing=False
        self.inject_extra_row=False

    def snapshot_once(self,source,dest):
        self.calls.append("snapshot")
        return snapshot_once(source,dest,now_fn=lambda:NOW)

    def baseline(self,*,source,snapshot,sidecar,snapshotter,clock):
        self.calls.append("original19")
        snap=snapshotter(source,snapshot)
        if not snap["published"]:
            raise AssertionError("snapshot unexpectedly failed")
        keys=self.original_keys[:-1] if self.inject_baseline_missing else self.original_keys
        db=open_writer(sidecar)
        try:
            for key in keys:
                st=record(db,key=key,family="frozen-v18",config="test",
                          output=OUTPUT,now=NOW,stock_as_of=HEARTBEAT,
                          executed=True,next_due=NOW+300)
                self.assertEqual(st,"RESEARCH_PROPOSAL_ONLY")
            if self.inject_extra_row:
                record(db,key="jap:Xanax",family="forbidden",config="none",
                       output=OUTPUT,now=NOW,stock_as_of=HEARTBEAT,
                       executed=True,next_due=NOW+300)
        finally:
            db.close()
        return {
            "status":"V63_FULL_MIRROR_EXECUTED",
            "results":[{"item_key":key,"status":"RESEARCH_PROPOSAL_ONLY"}
                       for key in keys],
            "proposal_count":len(keys),
            "native_error_count":0,
            "end_heartbeat_age_seconds":NOW-HEARTBEAT,
            "snapshot":snap,
        }

    def monkey(self,*,source,snapshot,sidecar,cache,snapshotter,clock):
        self.calls.append("monkey")
        self.assertEqual((source,snapshot,cache,sidecar),
             (self.source.resolve(),self.snapshot.resolve(),self.cache.resolve(),
              self.sidecar.resolve()))
        snap=snapshotter(source,snapshot)
        self.assertEqual(snap["status"],"PRIVATE_SNAPSHOT_READY")
        self.assertEqual(self.calls.count("snapshot"),1)
        if self.inject_no_monkey:
            return {"status":"V68_MONKEY_ABSTAIN","monkey_validator_status":"V66_CACHE_NOT_READY"}
        db=open_writer(sidecar)
        try:
            status=record(db,key=m.MONKEY,family=m.monkey.FAMILY,
                config=m.monkey.CONFIG,output=OUTPUT,now=NOW,
                stock_as_of=HEARTBEAT,executed=True,next_due=NOW+300)
        finally:
            db.close()
        self.assertEqual(status,"RESEARCH_PROPOSAL_ONLY")
        return {"status":m.monkey.SUCCESS,
                "monkey_validator_status":"V66_MONKEY_SELECTOR_VALIDATED",
                "cached_decisions":1176,"missing_decisions":0,
                "chosen_expert_index":20,"source_parity_one_slot":True}

    def run(self,**kwargs):
        return m.run(
            source=self.source,snapshot=self.snapshot,
            sidecar=self.sidecar,cache=self.cache,
            original_runner=self.baseline,monkey_runner=self.monkey,
            snapshotter=self.snapshot_once,
            capacity_probe=lambda:{"allowed":True},
            clock=lambda:NOW,**kwargs)

    def test_exact_20_saved_one_snapshot_no_v65_mutations(self):
        before_cache=self.cache.read_bytes()
        with sqlite3.connect(self.source) as con:
            before_data=con.execute("SELECT * FROM stock_history").fetchall()
        out=self.run()
        self.assertEqual(out["status"],"V69_FULL20_ISOLATED_SMOKE_PASSED")
        self.assertEqual(out["proposal_count"],20)
        self.assertEqual(out["persisted_count"],20)
        self.assertTrue(out["persisted_keys_exact"])
        self.assertTrue(out["monkey_family_exact"])
        self.assertEqual(out["persisted_invalid_keys"],[])
        self.assertFalse(out["model_20_admitted"])
        self.assertFalse(out["live_sidecar_written"])
        self.assertEqual(self.calls,["original19","snapshot","monkey"])
        self.assertEqual(self.cache.read_bytes(),before_cache)
        with sqlite3.connect(self.source) as con:
            after_data=con.execute("SELECT * FROM stock_history").fetchall()
        self.assertEqual(after_data,before_data)

    def test_incomplete_nineteen_does_not_run_monkey(self):
        self.inject_baseline_missing=True
        out=self.run()
        self.assertEqual(out["status"],"V69_BASELINE_NOT_READY")
        self.assertEqual(self.calls,["original19","snapshot"])
        self.assertEqual(out["baseline_count"],18)

    def test_incomplete_monkey_abstains_and_leaves_original19(self):
        self.inject_no_monkey=True
        out=self.run()
        self.assertEqual(out["status"],"V69_MONKEY_NOT_READY")
        with sqlite3.connect(self.sidecar) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM latest_predictions").fetchone()[0],19)

    def test_unexpected_twenty_first_item_blocks_success(self):
        self.inject_extra_row=True
        out=self.run()
        self.assertEqual(out["status"],"V69_SIDECAR_MISMATCH")
        self.assertEqual(out["persisted_count"],21)
        self.assertFalse(out["persisted_keys_exact"])

    def test_capacity_gate_before_snapshot(self):
        result=m.run(source=self.source,snapshot=self.snapshot,
           sidecar=self.sidecar,cache=self.cache,
           capacity_probe=lambda:{"allowed":False},
           original_runner=Mock(),monkey_runner=Mock())
        self.assertEqual(result["status"],"V69_DEFERRED_CPU_PRESSURE")
        self.assertFalse(self.sidecar.exists())

    def test_rejects_live_v65_sidecar(self):
        with self.assertRaises(ValueError):
            m.run(source=self.source,snapshot=self.snapshot,cache=self.cache,
                  sidecar=m.PRIVATE_LIVE,original_runner=Mock())

    def test_stale_baseline_snapshot_blocks_monkey(self):
        def stale_runner(**kwargs):
            out=self.baseline(**kwargs)
            out["end_heartbeat_age_seconds"]=181
            return out
        later=m.run(source=self.source,snapshot=self.snapshot,
            sidecar=self.sidecar,cache=self.cache,
            snapshotter=self.snapshot_once,original_runner=stale_runner,
            monkey_runner=self.monkey,
            capacity_probe=lambda:{"allowed":True},clock=lambda:NOW)
        self.assertEqual(later["status"],"V69_BASELINE_NOT_READY")
        self.assertNotIn("monkey",self.calls)

    def test_readback_rejects_stale_persisted_rows(self):
        out=self.run()
        self.assertEqual(out["status"],"V69_FULL20_ISOLATED_SMOKE_PASSED")
        check=m.verify_rows(self.sidecar,set(self.original_keys)|{m.MONKEY},
                            clock=lambda:NOW+250)
        self.assertEqual(len(check["persisted_invalid_keys"]),20)

    def test_error_in_baseline_is_never_called_twenty_successes(self):
        def failure(**kwargs):
            return {"status":"V63_SNAPSHOT_ERROR","results":[]}
        r=m.run(source=self.source,snapshot=self.snapshot,sidecar=self.sidecar,
          cache=self.cache,original_runner=failure,monkey_runner=Mock(),
          capacity_probe=lambda:{"allowed":True})
        self.assertEqual(r["status"],"V69_BASELINE_NOT_READY")
        self.assertFalse(self.sidecar.exists())


if __name__=="__main__":
    unittest.main()
