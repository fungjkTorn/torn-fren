"""V35 live-museum pilot: true V18 champion + specialist fail-closed contracts."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from services.private_v18_champion_worker_v35 import (
    single_tick, FROZEN_V18_PILOT, MAX_WAIT, REPLAN_STEP,
)
from services.private_challenger_adapter_v31 import (
    research_candidate, NATIVE_FLAG, DB_PATH_FLAG,
)


class V35ResearchOnlyTests(unittest.TestCase):
    def synthetic(self,folder,key):
        country,item=key.split(":",1)
        path=Path(folder)/"synthetic.db"
        begin=1790000000
        with sqlite3.connect(path) as con:
            con.executescript("""
            CREATE TABLE stock_history(
                timestamp INTEGER,country TEXT,item_name TEXT,
                quantity INTEGER,source TEXT);
            CREATE TABLE poll_heartbeats(
                timestamp INTEGER,success INTEGER,mode TEXT);
            CREATE TABLE collection_gaps(
                start_timestamp INTEGER,end_timestamp INTEGER,reason TEXT);
            """)
            data=[(begin+j*300,country,item,
                   120 if j%36<24 else 0,"synthetic") for j in range(1400)]
            con.executemany("INSERT INTO stock_history VALUES (?,?,?,?,?)",data)
            now=begin+1399*300+60
            con.execute("INSERT INTO poll_heartbeats VALUES (?,?,?)",
                        (now-20,1,"poll-cycle"))
        return path,now

    def test_actual_original_engine_produces_frozen_v18(self):
        for key,config in FROZEN_V18_PILOT.items():
            with self.subTest(key=key),tempfile.TemporaryDirectory() as directory:
                db,now=self.synthetic(directory,key)
                before=hashlib.sha256(db.read_bytes()).hexdigest()
                country,item=key.split(":",1)
                result=single_tick(db,country,item,config,now)
                self.assertEqual(result["status"],"RESEARCH_PROPOSAL_ONLY",
                                 str(result))
                self.assertEqual(result["model_generation"],"V18")
                self.assertEqual(result["model_config"],config)
                self.assertEqual(result["replan_step_seconds"],REPLAN_STEP)
                self.assertEqual(result["research_horizon_seconds"],MAX_WAIT)
                self.assertGreaterEqual(result["recommended_departure_timestamp"],now)
                self.assertLessEqual(result["recommended_departure_timestamp"],now+MAX_WAIT)
                self.assertFalse(result["probability_calibrated"])
                self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(),before)

    def test_adapter_produces_true_v18_private_response(self):
        with tempfile.TemporaryDirectory() as directory:
            db,now=self.synthetic(directory,"uni:Heather")
            env={NATIVE_FLAG:"1",DB_PATH_FLAG:str(db)}
            def mock_run(args,**kwargs):
                self.assertIn("services.private_v18_champion_worker_v35",args)
                self.assertIn("--config",args)
                self.assertIn("dyn3",args)
                self.assertEqual(kwargs["timeout"],35)
                return Mock(returncode=0,stderr="",stdout=json.dumps({
                    "status":"RESEARCH_PROPOSAL_ONLY","key":"uni:Heather",
                    "model_generation":"V18","model_config":"dyn3",
                    "probability_calibrated":False,
                    "recommended_departure_timestamp":now+300,
                    "recommended_arrival_timestamp":now+300+6360,
                    "replan_step_seconds":300,
                    "research_horizon_seconds":28800,
                }))
            result=research_candidate("uni","Heather",
                {"model_family":"V18","config_name":"dyn3"},"flower",
                env,now,run_worker=mock_run)
            self.assertTrue(result["champion_executed"],result)
            self.assertEqual(result["model_generation"],"V18")
            self.assertEqual(result["mode"],"PRIVATE_DIAGNOSTIC_NOT_LIVE")

    def test_specialists_do_not_fall_back_to_generic(self):
        env={NATIVE_FLAG:"1",DB_PATH_FLAG:"/no/dummy.db"}
        for country,item,family in [
            ("uni","Nessie Plushie","recent_phase_template"),
            ("jap","Xanax","japan_xanax_specialist"),
            ("chi","Panda Plushie","two_expert_extra_trees")
        ]:
            with self.subTest(item=item):
                x=research_candidate(country,item,
                    {"model_family":family,"config_name":None},"plushie",env)
                self.assertFalse(x["champion_executed"])
                self.assertEqual(x["status"],"SPECIALIST_OR_BASELINE_UNSUPPORTED")

    def test_specialist_baseline_only_is_captureable_without_false_wins(self):
        from unittest.mock import patch
        from services.private_champion_shadow_v29 import (
            make_shadow_snapshot,ENABLED_ENV,TOKEN_ENV,
        )
        from research.v31_shadow_evidence_capture import record_private_decision
        token="pilot-test-only-0123456789abcdef0123456789"
        when=1791499800
        def v2(country,item,record_audit):
            self.assertFalse(record_audit)
            travel=8940 if country=="jap" else 6360
            return {"display_prediction":{
                "recommended_leave_by_timestamp":when+1000,
                "recommended_arrival_timestamp":when+1000+travel}}
        with tempfile.TemporaryDirectory() as directory:
            ledger=Path(directory)/"evidence.db"
            for country,item in [("uni","Nessie Plushie"),("jap","Xanax")]:
                with patch("services.private_champion_shadow_v29.time.time",
                           return_value=when):
                    snapshot=make_shadow_snapshot(country,item,token,
                        v2_fn=v2,
                        environ={ENABLED_ENV:"1",TOKEN_ENV:token,
                                 NATIVE_FLAG:"1"})
                self.assertFalse(snapshot["champion_executed"])
                self.assertEqual(snapshot["challenger"]["status"],
                                 "SPECIALIST_OR_BASELINE_UNSUPPORTED")
                self.assertEqual(snapshot["baseline"]["status"],"available")
                result=record_private_decision(ledger,snapshot,
                    "pilot-museum-japan-v35",now=when)
                self.assertEqual(result["status"],"RECORDED")
            with sqlite3.connect(ledger) as con:
                self.assertEqual(con.execute(
                    "SELECT COUNT(*) FROM shadow_decisions "
                    "WHERE challenger_executed=0 AND v2_departure IS NOT NULL"
                    ).fetchone()[0],2)

    def test_only_two_frozen_v18_configs_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            db,now=self.synthetic(directory,"uni:Heather")
            self.assertEqual(set(FROZEN_V18_PILOT),{
                "uni:Heather","can:Wolverine Plushie"})
            result=single_tick(db,"uni","Heather","dyn8",now)
            self.assertEqual(result["status"],"NOT_APPROVED_FROZEN_V18_PILOT")
            x=research_candidate("uni","Heather",
               {"model_family":"V18","config_name":"dyn8"},"flower",
               {NATIVE_FLAG:"1",DB_PATH_FLAG:str(db)},now)
            self.assertEqual(x["status"],"SPECIALIST_OR_BASELINE_UNSUPPORTED")

    def test_no_native_challenger_when_disabled(self):
        x=research_candidate("uni","Heather",
            {"model_family":"V18","config_name":"dyn3"},"flower",{})
        self.assertFalse(x["champion_executed"])
        self.assertEqual(x["status"],"DISABLED")


if __name__=="__main__":unittest.main()
