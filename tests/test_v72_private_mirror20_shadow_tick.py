"""V72 scheduled 20-model candidate tests: retain V65 rollback and V48 isolation."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

from research import v72_private_mirror20_shadow_tick as v72
from research import v68_monkey_isolated_canary as monkey
from research.v38_prediction_store import record,open_writer
from research.v60_private_snapshot_probe import snapshot_once
from research.plushie_champions.common import TRAVEL_SECONDS

NOW=1791650000
HEARTBEAT=NOW-12
OVERLAY=Path(__file__).resolve().parents[1]/"deploy/systemd/v72-private-mirror20.conf"


class Scheduled20Tests(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        root=Path(d.name)
        self.source=root/"collector"/"live.db"
        self.source.parent.mkdir()
        self.snapshot=root/"private"/"snapshot.db"
        self.sidecar=root/"private"/"predictions.db"
        self.cache=root/"cache"/"expert.db"
        self.cache.parent.mkdir()
        self.cache.write_bytes(b"fixture only; mock never reads cache")
        self.calls=[]
        self.rows=v72.exact_roster()
        self.monkey_ready=True
        self.original_mode="EXECUTED_RESEARCH_ONLY"
        self.original_fail=None
        with sqlite3.connect(self.source) as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("""CREATE TABLE stock_history(
                id INTEGER PRIMARY KEY,timestamp INTEGER,country TEXT,
                item_name TEXT,quantity INTEGER,source TEXT)""")
            c.execute("""CREATE TABLE poll_heartbeats(
                timestamp INTEGER,mode TEXT,success INTEGER)""")
            c.execute("""CREATE TABLE collection_gaps(
                start_timestamp INTEGER,end_timestamp INTEGER)""")
            c.execute("INSERT INTO stock_history VALUES(1,?,?,?,?,?)",
                     (NOW-300,"arg","Monkey Plushie",40,"test"))
            c.execute("INSERT INTO poll_heartbeats VALUES(?,'poll-cycle',1)",
                     (HEARTBEAT,))

    def snap(self,src,dst):
        self.calls.append("snapshot")
        return snapshot_once(src,dst,now_fn=lambda:NOW)

    def mock_monkey(self,*,source,snapshot,cache,sidecar,snapshotter,clock):
        self.calls.append("monkey")
        self.assertEqual((source,snapshot,cache,sidecar),
                         (self.source.resolve(),self.snapshot.resolve(),
                          self.cache.resolve(),self.sidecar.resolve()))
        ready=snapshotter(source,snapshot)
        self.assertTrue(ready["published"])
        self.assertEqual(self.calls.count("snapshot"),1)
        if not self.monkey_ready:
            return {"status":"V68_MONKEY_ABSTAIN",
                    "monkey_validator_status":"V66_CACHE_NOT_READY"}
        c=open_writer(sidecar)
        try:
            departure=NOW+2400
            status=record(c,key=monkey.KEY,family=monkey.FAMILY,
                          config=monkey.CONFIG,output={
                           "status":"RESEARCH_PROPOSAL_ONLY",
                           "recommended_departure_timestamp":departure,
                           "recommended_arrival_timestamp":departure+TRAVEL_SECONDS["arg"],
                           "quantity_threshold":30,"grace_seconds":10,
                           "replan_step_seconds":300,"probability_calibrated":False,
                          },now=NOW,stock_as_of=HEARTBEAT,executed=True,
                          next_due=NOW+300)
        finally:
            c.close()
        self.assertEqual(status,"RESEARCH_PROPOSAL_ONLY")
        return {"status":monkey.SUCCESS,"monkey_validator_status":"V66_MONKEY_SELECTOR_VALIDATED",
                "cached_decisions":1176,"missing_decisions":0,
                "chosen_expert_index":12,"source_parity_one_slot":True}

    def mock_original(self,**kwargs):
        self.calls.append("original19")
        self.assertEqual(kwargs["stock_db"],self.snapshot.resolve())
        self.assertEqual(kwargs["sidecar_db"],self.sidecar.resolve())
        self.assertEqual(tuple(sorted(kwargs["approved_keys"])),self.rows)
        self.assertEqual(kwargs["max_jobs"],19)
        self.assertEqual(kwargs["worker_seconds"],30)
        self.assertEqual(kwargs["budget_seconds"],220)
        self.assertEqual(kwargs["max_rows"],10000)
        self.assertTrue(kwargs["execute"])
        self.assertTrue(kwargs["with_xanax"])
        self.assertTrue(kwargs["with_redfox"])
        self.assertNotIn("active",kwargs)
        if self.original_mode!="EXECUTED_RESEARCH_ONLY":
            return {"mode":self.original_mode,"executed":[]}
        c=open_writer(kwargs["sidecar_db"])
        results=[]
        try:
            for key in self.rows:
                country=key.split(":",1)[0]
                departure=NOW+2400
                out={"status":"RESEARCH_PROPOSAL_ONLY",
                     "recommended_departure_timestamp":departure,
                     "recommended_arrival_timestamp":departure+TRAVEL_SECONDS[country],
                     "quantity_threshold":30,"grace_seconds":10,
                     "replan_step_seconds":300,"probability_calibrated":False}
                if key==self.original_fail:
                    out={"status":"WORKER_TIMEOUT"}
                status=record(c,key=key,family="original",config="frozen",
                              output=out,now=NOW,stock_as_of=HEARTBEAT,
                              executed=True,next_due=NOW+300)
                results.append({"item_key":key,"status":status})
        finally:
            c.close()
        return {"mode":"EXECUTED_RESEARCH_ONLY","executed":results}

    def tick(self,*,clock=NOW,capacity=True):
        return v72.tick(source=self.source,snapshot=self.snapshot,
             sidecar=self.sidecar,cache=self.cache,snapshotter=self.snap,
             monkey_runner=self.mock_monkey,infer=self.mock_original,
             capacity_probe=lambda:{"allowed":capacity},
             clock=lambda:clock)

    def read_rows(self):
        with sqlite3.connect(self.sidecar) as c:
            return c.execute("""SELECT item_key,status,departure,arrival
                FROM latest_predictions ORDER BY item_key""").fetchall()

    def test_full_twenty_monkey_first_fresh_mirror_separate_sidecar(self):
        result=self.tick()
        self.assertEqual(self.calls,["snapshot","monkey","original19"])
        self.assertEqual(result["status"],"V72_EXECUTED_RESEARCH_ONLY")
        self.assertEqual(result["proposal_count"],20)
        self.assertEqual(result["expected_roster_size"],20)
        self.assertEqual(result["original_19_proposal_count"],19)
        self.assertEqual(result["monkey_proposal_count"],1)
        self.assertTrue(result["snapshot_fresh_after_cycle"])
        self.assertEqual(result["end_heartbeat_age_seconds"],12)
        self.assertTrue(result["monkey_source_parity"])
        self.assertFalse(result["v65_sidecar_written"])
        self.assertFalse(result["published_to_website"])
        self.assertEqual(len(self.read_rows()),20)
        self.assertEqual({r[0] for r in self.read_rows()},
                         set(self.rows)|{monkey.KEY})

    def test_incomplete_monkey_records_explicit_null_departure_but_original19_runs(self):
        self.monkey_ready=False
        out=self.tick()
        self.assertEqual(out["status"],"V72_EXECUTED_RESEARCH_ONLY")
        self.assertEqual(out["proposal_count"],19)
        self.assertEqual(out["monkey_proposal_count"],0)
        self.assertEqual(out["original_19_proposal_count"],19)
        self.assertEqual(self.calls,["snapshot","monkey","original19"])
        rows={r[0]:r for r in self.read_rows()}
        self.assertEqual(len(rows),20)
        self.assertEqual(rows[monkey.KEY][1],"MONKEY_CACHE_OR_SOURCE_ABSTENTION")
        self.assertIsNone(rows[monkey.KEY][2])
        self.assertIsNone(rows[monkey.KEY][3])

    def test_new_failed_monkey_overwrites_previous_successful_departure(self):
        self.tick()
        self.monkey_ready=False
        second=self.tick()
        self.assertEqual(second["monkey_proposal_count"],0)
        rows={r[0]:r for r in self.read_rows()}
        self.assertEqual(rows[monkey.KEY][1],"MONKEY_CACHE_OR_SOURCE_ABSTENTION")
        self.assertIsNone(rows[monkey.KEY][2])

    def test_one_original_failure_reported_not_counted_as_proposal(self):
        self.original_fail=self.rows[0]
        out=self.tick()
        self.assertEqual(out["proposal_count"],19)
        self.assertEqual(out["original_19_proposal_count"],18)
        self.assertEqual(len(self.read_rows()),20)

    def test_capacity_gate_defers_before_snapshot(self):
        result=self.tick(capacity=False)
        self.assertEqual(result["status"],"V72_DEFERRED_CPU_PRESSURE")
        self.assertEqual(self.calls,[])
        self.assertFalse(self.sidecar.exists())

    def test_bad_snapshot_abstains_before_monkey_and_original19(self):
        out=v72.tick(source=self.source,snapshot=self.snapshot,
            sidecar=self.sidecar,cache=self.cache,
            snapshotter=lambda a,b:{"status":"SOURCE_HEARTBEAT_STALE","published":False},
            monkey_runner=self.mock_monkey,infer=self.mock_original,
            capacity_probe=lambda:{"allowed":True},clock=lambda:NOW)
        self.assertEqual(out["status"],"V72_NO_FRESH_SNAPSHOT")
        self.assertEqual(self.calls,[])
        self.assertFalse(self.sidecar.exists())

    def test_snapshot_age_after_run_reported_not_called_fresh(self):
        self.tick()
        # Mock final-age guard only. Real run_tick itself refuses stale
        # source at the start; historic work may age out mid-cycle.
        with patch.object(v72,"source_age",return_value=190):
            out=self.tick()
        self.assertEqual(out["status"],"V72_SNAPSHOT_EXPIRED_POST_CYCLE")
        self.assertFalse(out["snapshot_fresh_after_cycle"])

    def test_original_runner_pressure_deferred_is_not_20_success(self):
        self.original_mode="DEFERRED_CPU_PRESSURE"
        out=self.tick()
        self.assertTrue(out["status"].startswith("V72_DEFERRED_"))
        self.assertEqual(out["original_19_executed_count"],0)
        self.assertEqual(out["proposal_count"],1)

    def test_rejects_prior_v65_sidecar_as_destination(self):
        with self.assertRaises(ValueError):
            v72.tick(source=self.source,snapshot=self.snapshot,
                sidecar=v72.V65_SIDECAR,cache=self.cache,
                capacity_probe=lambda:{"allowed":True})
        self.assertEqual(self.calls,[])

    def test_systemd_override_changes_only_private_execstart(self):
        raw=OVERLAY.read_text()
        execs=[ln for ln in raw.splitlines() if ln.startswith("ExecStart")]
        self.assertEqual(execs,[
            "ExecStart=",
            "ExecStart=/home/ubuntu/torn-fren-v38-probe/.venv/bin/python -m research.v72_private_mirror20_shadow_tick",
        ])
        for forbidden in ("CPUQuota=","MemoryMax=","ReadWritePaths=",
                          "TORN_FREN_V38_EXPERIMENTAL_API","torn-fren-poller.service"):
            self.assertNotIn(forbidden,raw)

    def test_monkey_model_never_added_to_original_nineteen(self):
        self.assertEqual(len(self.rows),19)
        self.assertNotIn(monkey.KEY,self.rows)
        self.assertEqual(v72.MONKEY_CACHE,monkey.CACHE)
        self.assertNotEqual(v72.SIDECAR,v72.V65_SIDECAR)

if __name__=="__main__":
    unittest.main()
