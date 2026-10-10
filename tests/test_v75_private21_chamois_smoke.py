"""V75 isolated 21-model smoke and guard regression tests."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research import v75_private21_chamois_smoke as m
from research import v74_chamois_isolated_canary as chamois
from research import v72_private_mirror20_shadow_tick as v72
from research.v60_private_snapshot_probe import snapshot_once
from research.v38_prediction_store import open_writer,record
from research.plushie_champions.common import TRAVEL_SECONDS

NOW=1791650000
HB=NOW-15


class TwentyOneResearchTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        self.source=root/"collector"/"stock.db"
        self.source.parent.mkdir()
        self.snap=root/"research"/"frozen.db"
        self.sidecar=root/"research"/"21.db"
        self.cache=root/"cache"/"expert.db"
        self.cache.parent.mkdir()
        self.cache.write_bytes(b"fixture")
        self.calls=[]
        self.chamois_ready=True
        self.baseline_ready=True
        with sqlite3.connect(self.source) as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("CREATE TABLE stock_history(id INTEGER PRIMARY KEY,timestamp INTEGER,country TEXT,item_name TEXT,quantity INTEGER,source TEXT)")
            con.execute("CREATE TABLE poll_heartbeats(timestamp INTEGER,mode TEXT,success INTEGER)")
            con.execute("CREATE TABLE collection_gaps(start_timestamp INTEGER,end_timestamp INTEGER)")
            con.execute("INSERT INTO stock_history VALUES(1,?,?,?,?,?)",(NOW-300,"swi","Chamois Plushie",10,"fixture"))
            con.execute("INSERT INTO poll_heartbeats VALUES(?,'poll-cycle',1)",(HB,))

    def backup(self,a,b):
        self.calls.append("snapshot")
        return snapshot_once(a,b,now_fn=lambda:NOW)

    def _record(self,con,key):
        country=key.split(":",1)[0]
        departure=NOW+2100
        return record(con,key=key,
            family="online_template_expert" if key==chamois.KEY else "test_original",
            config=chamois.CONFIG if key==chamois.KEY else "frozen",
            output={"status":"RESEARCH_PROPOSAL_ONLY",
                    "recommended_departure_timestamp":departure,
                    "recommended_arrival_timestamp":departure+TRAVEL_SECONDS[country],
                    "quantity_threshold":30,"grace_seconds":10,
                    "replan_step_seconds":300,"probability_calibrated":False},
            now=NOW,stock_as_of=HB,executed=True,next_due=NOW+300)

    def chamois(self,**args):
        self.calls.append("chamois")
        self.assertTrue(args["snapshotter"](None,None)["published"])
        if not self.chamois_ready:
            return {"status":"V74_CHAMOIS_ABSTAIN",
                    "chamois_validator_status":"V66_CACHE_NOT_READY",
                    "missing_decisions":1}
        con=open_writer(args["sidecar"])
        try:
            self._record(con,chamois.KEY)
        finally:
            con.close()
        return {"status":chamois.SUCCESS,
                "chamois_validator_status":"V66_CHAMOIS_SELECTOR_VALIDATED",
                "cached_decisions":2304,"missing_decisions":0,
                "chosen_expert_index":0,"source_parity_one_slot":True}

    def baseline(self,**args):
        self.calls.append("baseline")
        self.assertTrue(args["snapshotter"](None,None)["published"])
        self.assertEqual(args["capacity_probe"](),{"allowed":True})
        if not self.baseline_ready:
            return {"status":"V72_DEFERRED_PRESSURE",
                    "snapshot_fresh_after_cycle":False}
        con=open_writer(args["sidecar"])
        try:
            for key in set(v72.exact_roster())|{v72.monkey.KEY}:
                self._record(con,key)
        finally:
            con.close()
        return {
            "status":"V72_EXECUTED_RESEARCH_ONLY",
            "snapshot_fresh_after_cycle":True,
            "original_19_proposal_count":19,
            "monkey_proposal_count":1,
            "proposal_count":20,
            "original_19_error_count":0,
            "original_19_stale_count":0,
            "end_heartbeat_age_seconds":112,
        }

    def run_it(self,cap=True):
        return m.tick(source=self.source,snapshot=self.snap,
            sidecar=self.sidecar,cache=self.cache,
            snapshotter=self.backup,chamois_runner=self.chamois,
            baseline_runner=self.baseline,
            capacity_probe=lambda:{"allowed":cap},clock=lambda:NOW)

    def rows(self):
        with sqlite3.connect(self.sidecar) as con:
            return con.execute("SELECT item_key,status,departure FROM latest_predictions").fetchall()

    def test_full21_once_one_snapshot_chamois_first_and_20_unmodified(self):
        out=self.run_it()
        self.assertEqual(out["status"],m.SUCCESS)
        self.assertEqual(out["total_proposals"],21)
        self.assertEqual(out["model_roster_size"],21)
        self.assertEqual(out["chamois_proposals"],1)
        self.assertEqual(out["v72_original_19_proposals"],19)
        self.assertEqual(out["v72_monkey_proposals"],1)
        self.assertTrue(out["source_fresh_after_cycle"])
        self.assertEqual(self.calls,["snapshot","chamois","baseline"])
        self.assertEqual(len(self.rows()),21)
        self.assertEqual({r[0] for r in self.rows()},
                         set(v72.exact_roster())|{v72.monkey.KEY,chamois.KEY})
        self.assertFalse(out["website_sidecar_written"])
        self.assertFalse(out["v72_sidecar_written"])
        self.assertFalse(out["model_21_scheduled"])

    def test_chamois_cache_gap_explicit_abstention_preserves_20(self):
        self.chamois_ready=False
        out=self.run_it()
        self.assertEqual(out["status"],m.SUCCESS)
        self.assertEqual(out["total_proposals"],20)
        self.assertEqual(out["chamois_proposals"],0)
        self.assertEqual(len(self.rows()),21)
        ch=[r for r in self.rows() if r[0]==chamois.KEY][0]
        self.assertEqual(ch[1],"CHAMOIS_CACHE_OR_SOURCE_ABSTENTION")
        self.assertIsNone(ch[2])

    def test_existing_chamois_prediction_replaced_by_new_abstention(self):
        self.run_it()
        self.chamois_ready=False
        self.run_it()
        ch=[r for r in self.rows() if r[0]==chamois.KEY][0]
        self.assertEqual(ch[1],"CHAMOIS_CACHE_OR_SOURCE_ABSTENTION")
        self.assertIsNone(ch[2])

    def test_cpu_pressure_blocks_before_snapshot(self):
        r=self.run_it(cap=False)
        self.assertEqual(r["status"],"V75_DEFERRED_CPU_PRESSURE")
        self.assertEqual(self.calls,[])
        self.assertFalse(self.sidecar.exists())

    def test_bad_snapshot_blocks_both_canaries(self):
        result=m.tick(source=self.source,snapshot=self.snap,
            sidecar=self.sidecar,cache=self.cache,
            snapshotter=lambda a,b:{"status":"SOURCE_HEARTBEAT_STALE","published":False},
            chamois_runner=self.chamois,baseline_runner=self.baseline,
            capacity_probe=lambda:{"allowed":True},clock=lambda:NOW)
        self.assertEqual(result["status"],"V75_SNAPSHOT_NOT_READY")
        self.assertEqual(self.calls,[])

    def test_existing_v72_sidecar_never_accepted_for_test(self):
        with self.assertRaises(ValueError):
            m.tick(source=self.source,snapshot=self.snap,
                   sidecar=v72.SIDECAR,cache=self.cache,
                   capacity_probe=lambda:{"allowed":True})
        self.assertEqual(self.calls,[])

    def test_baseline_failure_not_labeled_success(self):
        self.baseline_ready=False
        r=self.run_it()
        self.assertEqual(r["status"],"V75_BASELINE_NOT_READY")
        self.assertEqual(r["total_proposals"],1)

    def test_schema_and_pinned_identity(self):
        self.assertEqual(chamois.KEY,"swi:Chamois Plushie")
        self.assertEqual(chamois.CONFIG,"original_24_experts_3d_resolved_selector")
        self.assertNotIn(chamois.KEY,v72.exact_roster())
        self.assertNotEqual(m.SIDECAR,v72.SIDECAR)


if __name__=="__main__":
    unittest.main()
