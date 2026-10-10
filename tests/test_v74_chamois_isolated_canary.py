"""V74 canary records Chamois ONLY in isolated research SQLite sidecar."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from research import v74_chamois_isolated_canary as m
from research.v60_private_snapshot_probe import snapshot_once

NOW=1791650000
HEARTBEAT=NOW-10


def make_live_source(path):
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("""CREATE TABLE stock_history(
            id INTEGER PRIMARY KEY,timestamp INTEGER,country TEXT,
            item_name TEXT,quantity INTEGER,source TEXT)""")
        db.execute("CREATE TABLE poll_heartbeats(timestamp INTEGER,mode TEXT,success INTEGER)")
        db.execute("CREATE TABLE collection_gaps(start_timestamp INTEGER,end_timestamp INTEGER)")
        db.execute("INSERT INTO stock_history VALUES(1,?,?,?,?,?)",
                   (NOW-900,"swi","Chamois Plushie",40,"synthetic"))
        db.execute("INSERT INTO poll_heartbeats VALUES(?,'poll-cycle',1)",(HEARTBEAT,))


class ChamoisIsolatedTests(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        root=Path(d.name)
        self.source=root/"collector"/"stock.db"
        self.source.parent.mkdir()
        make_live_source(self.source)
        self.mirror=root/"private"/"mirror.db"
        self.sidecar=root/"private"/"v74_canary.db"
        self.cache=root/"private"/"v48.db"
        self.cache.parent.mkdir()
        self.cache.write_bytes(b"read-only-fixture")
        self.proof={
            "status":"V66_CHAMOIS_SELECTOR_VALIDATED",
            "item_key":"swi:Chamois Plushie",
            "invalid_rows":0,"missing_decisions":0,
            "cached_decisions":1176,
            "source_parity_one_slot":True,
            "chosen_expert_index":20,
            "recommended_departure_timestamp":NOW+1800,
        }

    def backup(self,src,dst):
        return snapshot_once(src,dst,now_fn=lambda:NOW)

    def run_canary(self,proof=None,now=NOW,**kwargs):
        validator=Mock(return_value=self.proof if proof is None else proof)
        res=m.canary(source=self.source,snapshot=self.mirror,cache=self.cache,
                     sidecar=self.sidecar,snapshotter=self.backup,
                     validator=validator,clock=lambda:now,**kwargs)
        return res,validator

    def test_success_only_records_to_separate_canary_sidecar(self):
        # A read-only online backup can legitimately change the main SQLite
        # file's physical bytes through WAL checkpoint coordination.
        # Verify the collector's logical data is identical, not file bytes.
        with sqlite3.connect(f"file:{self.source}?mode=ro",uri=True) as source:
            live_original=(
                source.execute("SELECT * FROM stock_history ORDER BY id").fetchall(),
                source.execute("SELECT * FROM poll_heartbeats").fetchall(),
            )
        v48_original=self.cache.read_bytes()
        out,validator=self.run_canary()
        self.assertEqual(out["status"],m.SUCCESS)
        self.assertEqual(out["chosen_expert_index"],20)
        self.assertTrue(out["isolated_canary_row_written"])
        self.assertFalse(out["model_21_admitted"])
        self.assertFalse(out["published_to_website"])
        self.assertFalse(out["live_prediction_sidecar_written"])
        self.assertTrue(self.sidecar.is_file())
        with sqlite3.connect(self.sidecar) as db:
            row=db.execute("""SELECT item_key,status,model_family,model_config,
                       departure,arrival,stock_as_of FROM latest_predictions""").fetchone()
        self.assertEqual(row,(
            "arg:Monkey Plushie","RESEARCH_PROPOSAL_ONLY",
            m.FAMILY,m.CONFIG,NOW+1800,NOW+1800+6960,HEARTBEAT))
        with sqlite3.connect(f"file:{self.source}?mode=ro",uri=True) as source:
            live_after=(
                source.execute("SELECT * FROM stock_history ORDER BY id").fetchall(),
                source.execute("SELECT * FROM poll_heartbeats").fetchall(),
            )
        self.assertEqual(live_after,live_original)
        self.assertEqual(self.cache.read_bytes(),v48_original)
        self.assertEqual(validator.call_args.args,(self.mirror,self.cache))

    def test_incomplete_cache_never_writes_prediction(self):
        proof=dict(self.proof,status="V66_CACHE_NOT_READY",missing_decisions=24)
        out,_=self.run_canary(proof)
        self.assertEqual(out["status"],"V74_MONKEY_ABSTAIN")
        self.assertFalse(self.sidecar.exists())

    def test_missing_source_parity_never_writes_prediction(self):
        proof=dict(self.proof,source_parity_one_slot=False)
        out,_=self.run_canary(proof)
        self.assertEqual(out["status"],"V68_REJECTED_INCOMPLETE_PROOF")
        self.assertFalse(self.sidecar.exists())

    def test_departure_in_the_past_never_writes_prediction(self):
        proof=dict(self.proof,recommended_departure_timestamp=NOW-1)
        out,_=self.run_canary(proof)
        self.assertEqual(out["status"],"V68_STALE_OR_PASSED_DEPARTURE")
        self.assertFalse(self.sidecar.exists())

    def test_snapshot_stale_before_inference_never_calls_validator(self):
        proof=Mock(return_value=self.proof)
        out=m.canary(source=self.source,snapshot=self.mirror,cache=self.cache,
                     sidecar=self.sidecar,snapshotter=self.backup,
                     validator=proof,clock=lambda:NOW+300)
        self.assertEqual(out["status"],"V68_STALE_SNAPSHOT_BEFORE_VALIDATION")
        proof.assert_not_called()
        self.assertFalse(self.sidecar.exists())

    def test_snapshot_retry_failure_abstains_without_old_copy_reuse(self):
        calls=Mock()
        out=m.canary(source=self.source,snapshot=self.mirror,cache=self.cache,
             sidecar=self.sidecar,snapshotter=lambda a,b:{"published":False,
                  "status":"SOURCE_HEARTBEAT_STALE"},validator=calls)
        self.assertEqual(out["status"],"V68_NO_FRESH_SNAPSHOT")
        calls.assert_not_called()
        self.assertFalse(self.sidecar.exists())

    def test_code_guard_rejects_main_live_sidecar(self):
        with self.assertRaises(ValueError):
            m.canary(source=self.source,snapshot=self.mirror,cache=self.cache,
                     sidecar=m.ACTIVE,validator=Mock())

    def test_unverified_different_key_does_not_write(self):
        proof=dict(self.proof,item_key="arg:Monkey Plushie")
        out,_=self.run_canary(proof)
        self.assertEqual(out["status"],"V68_REJECTED_INCOMPLETE_PROOF")
        self.assertFalse(self.sidecar.exists())

    def test_no_ghost_prediction_from_validation_exception(self):
        def bad(*args,**kwargs):
            raise ValueError("no publication")
        out=m.canary(source=self.source,snapshot=self.mirror,cache=self.cache,
              sidecar=self.sidecar,snapshotter=self.backup,validator=bad,
              clock=lambda:NOW)
        self.assertEqual(out["status"],"V68_VALIDATION_ERROR")
        self.assertFalse(self.sidecar.exists())
        self.assertNotIn("no publication",str(out))

    def test_guard_rejects_shared_cache_and_sidecar(self):
        with self.assertRaises(ValueError):
            m.canary(source=self.source,snapshot=self.mirror,cache=self.cache,
                sidecar=self.cache,validator=Mock())


if __name__=="__main__":
    unittest.main()
