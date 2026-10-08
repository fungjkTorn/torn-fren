"""Research-only V31 private challenger: no main routing, no API keys."""
from __future__ import annotations
from dataclasses import asdict
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from services.frozen_candidate_worker_v31 import (
    inspect_live_source, frozen_single_tick
)
from services.private_challenger_adapter_v31 import (
    research_candidate, MASTER_ENV, DB_PATH_FLAG, NATIVE_FLAG
)
from services.private_champion_shadow_v29 import (
    make_shadow_snapshot, ENABLED_ENV, TOKEN_ENV
)


class PrivateChallengerTests(unittest.TestCase):
    def synthetic(self,folder):
        from services import plushie_flower_dynamic_planner_v19 as planner
        path=Path(folder)/"fake.db"
        begin=1790000000
        with sqlite3.connect(path) as con:
            con.executescript("""
            CREATE TABLE stock_history (
                timestamp INTEGER, country TEXT, item_name TEXT,
                quantity INTEGER, source TEXT);
            CREATE TABLE poll_heartbeats (
                timestamp INTEGER, success INTEGER, mode TEXT);
            CREATE TABLE collection_gaps (
                start_timestamp INTEGER,end_timestamp INTEGER,reason TEXT);
            """)
            rows=[]
            for j in range(1400):
                q=120 if j%36 <24 else 0
                rows.append((begin+j*300,"can","Fire Hydrant",q,"synthetic"))
            con.executemany("INSERT INTO stock_history VALUES (?,?,?,?,?)",rows)
            now=begin+1399*300+60
            con.execute("INSERT INTO poll_heartbeats VALUES (?,?,?)",
                        (now-20,1,"poll-cycle"))
        master=Path(folder)/"master.json"
        master.write_text(json.dumps({"settings":{"options":{
            "max_wait":43200,"departure_grid":900,"replan_step":900}},
            "results":{"can:Fire Hydrant":{
                "status":"complete",
                "selected_on_training":{"config":asdict(planner.configs()[0])}
            }}}))
        return path,master,now

    def test_challenger_flag_is_independent_and_off_by_default(self):
        r=research_candidate("can","Fire Hydrant",
                 {"model_family":"v21","config_name":"dyn1"},"other",environ={})
        self.assertEqual(r["status"],"DISABLED")
        self.assertFalse(r["champion_executed"])

    def test_stale_heartbeat_and_future_records_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            db,master,now=self.synthetic(folder)
            self.assertEqual(inspect_live_source(db,now)["status"],"FRESH")
            self.assertEqual(inspect_live_source(db,now+200)["status"],
                             "COLLECTOR_STALE_OR_NO_HEARTBEAT")
            self.assertEqual(inspect_live_source(db,now-300)["status"],
                             "FUTURE_RECORDS_PRESENT")
            with sqlite3.connect(db) as con:
                con.execute("INSERT INTO collection_gaps VALUES (?,?,?)",
                            (now-30,now+50,"test-gap"))
            self.assertEqual(inspect_live_source(db,now)["status"],
                             "COLLECTION_GAP_CROSSES_RECENT_POLL")

    def test_original_versioned_generic_produces_private_single_tick(self):
        with tempfile.TemporaryDirectory() as folder:
            db,master,now=self.synthetic(folder)
            before=hashlib.sha256(db.read_bytes()).hexdigest()
            proposal=frozen_single_tick(db,master,"v21","can","Fire Hydrant",now)
            self.assertEqual(proposal["status"],"RESEARCH_PROPOSAL_ONLY",
                             repr(proposal))
            self.assertEqual(proposal["model_config"],"dyn1")
            self.assertFalse(proposal["probability_calibrated"])
            self.assertGreaterEqual(proposal["recommended_departure_timestamp"],now)
            self.assertLessEqual(proposal["recommended_departure_timestamp"],now+43200)
            self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(),before)

    def test_adapter_rejects_mismatch_and_preserves_baseline(self):
        with tempfile.TemporaryDirectory() as folder:
            db,master,now=self.synthetic(folder)
            env={NATIVE_FLAG:"1",DB_PATH_FLAG:str(db),MASTER_ENV["v21"]:str(master)}
            selected={"model_family":"v21","config_name":"dyn1"}
            def runner(args,**kwargs):
                self.assertIn("--version",args)
                self.assertIn("v21",args)
                return Mock(returncode=0,stdout=json.dumps({
                   "status":"RESEARCH_PROPOSAL_ONLY","model_generation":"v21",
                   "model_config":"dyn1","key":"can:Fire Hydrant",
                   "recommended_departure_timestamp":now+900,
                   "recommended_arrival_timestamp":now+900+1620,
                   "replan_step_seconds":900,"research_horizon_seconds":43200,
                   "probability_calibrated":False}),stderr="")
            valid=research_candidate("can","Fire Hydrant",selected,"other",
                                     env,now,run_worker=runner)
            self.assertTrue(valid["champion_executed"])
            self.assertFalse(valid["chance_calibrated"])
            bad=research_candidate("can","Fire Hydrant",
                {"model_family":"v21","config_name":"dyn7"},"other",
                env,now,run_worker=runner)
            self.assertEqual(bad["status"],"FROZEN_CONFIG_IDENTITY_MISMATCH")
            self.assertFalse(bad["champion_executed"])

    def test_authenticated_shadow_reports_research_only_and_keeps_v2(self):
        import os
        registry=Path(__file__).resolve().parents[1]/"research"/"all_236_champions_v26.json"
        token="long-research-test-token-123456789012345678"
        def v2(country,item,record_audit):
            self.assertFalse(record_audit)
            return {"display_prediction":{
                "recommended_leave_by_timestamp":1792000000,
                "recommended_arrival_timestamp":1792001620}}
        def challenger(country,item,selection,category,environ):
            return {"status":"RESEARCH_PROPOSAL_ONLY","champion_executed":True,
                "recommended_departure_timestamp":1792000600}
        result=make_shadow_snapshot("can","Fire Hydrant",token,v2_fn=v2,
            environ={ENABLED_ENV:"1",TOKEN_ENV:token},
            registry_path=registry,challenger_fn=challenger)
        self.assertTrue(result["champion_executed"])
        self.assertFalse(result["candidate_promoted"])
        self.assertEqual(result["default_live_routing"],"UNCHANGED")
        self.assertEqual(result["baseline"]["recommended_leave_by_timestamp"],1792000000)
        self.assertEqual(result["challenger"]["recommended_departure_timestamp"],1792000600)


if __name__=="__main__":
    unittest.main()
