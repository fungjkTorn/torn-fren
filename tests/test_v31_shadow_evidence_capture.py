import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research.v31_shadow_evidence_capture import record_private_decision


def private_snapshot():
    return {
      "schema":"torn-fren-private-research-shadow-v29",
      "mode":"READ_ONLY_DIAGNOSTIC",
      "generated_at":1792000100,
      "default_live_routing":"UNCHANGED",
      "key":"can:Fire Hydrant",
      "candidate_promoted":False,
      "chance_calibrated":False,
      "candidate_model_family":"v21",
      "candidate_config":"dyn13",
      "champion_executed":True,
      "private_token":"TOP_SECRET_SHOULD_NEVER_BE_STORED",
      "baseline":{"status":"available",
             "recommended_leave_by_timestamp":1792000900,
             "recommended_arrival_timestamp":1792002520,
             "api_key":"DO_NOT_STORE_API_KEY"},
      "challenger":{"status":"RESEARCH_PROPOSAL_ONLY",
             "champion_executed":True,
             "recommended_departure_timestamp":1792000300,
             "recommended_arrival_timestamp":1792001920,
             "master_path":"/private/collector/source.json"}
    }


class EvidenceCaptureTests(unittest.TestCase):
    def test_unique_5min_tick_and_no_secrets(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/"shadow_only.db"
            snap=private_snapshot()
            x=record_private_decision(db,snap,"pilot-V31",now=1792000100)
            y=record_private_decision(db,snap,"pilot-V31",now=1792000170)
            snap["generated_at"]=1792000400
            z=record_private_decision(db,snap,"pilot-V31",now=1792000400)
            self.assertEqual(x["status"],"RECORDED")
            self.assertEqual(y["status"],"DUPLICATE_TICK_IGNORED")
            self.assertEqual(z["status"],"RECORDED")
            with sqlite3.connect(db) as con:
                self.assertEqual(con.execute("select count(*) from shadow_decisions").fetchone()[0],2)
                self.assertEqual(con.execute("select sum(challenger_executed) from shadow_decisions").fetchone()[0],2)
                row=con.execute("select resolution_status,v2_departure,challenger_departure from shadow_decisions limit 1").fetchone()
                self.assertEqual(row,("PENDING",1792000900,1792000300))
                metadata=con.execute("SELECT source_schema,source_generated_at FROM shadow_decisions ORDER BY id LIMIT 1").fetchone()
                self.assertEqual(metadata,("torn-fren-v31-shadow-evidence-capture-v1",1792000100))
            text=db.read_bytes().decode("latin1")
            for forbidden in ("TOP_SECRET_SHOULD_NEVER_BE_STORED","DO_NOT_STORE_API_KEY","/private/collector/source.json"):
                self.assertNotIn(forbidden,text)

    def test_no_challenger_still_counts_for_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"evidence.db"
            snap=private_snapshot()
            snap["champion_executed"]=False
            snap["challenger"]={"status":"DISABLED","champion_executed":False}
            out=record_private_decision(p,snap,"pilot-V31",now=1792000100)
            self.assertFalse(out["challenger_executed"])
            with sqlite3.connect(p) as con:
                row=con.execute("select challenger_executed,challenger_departure,resolution_status from shadow_decisions").fetchone()
                self.assertEqual(row,(0,None,"PENDING"))

    def test_reject_stale_backdated_or_future_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/"private.db"
            snap=private_snapshot()
            with self.assertRaises(ValueError):
                record_private_decision(file,snap,"pilot-V31",now=1792000400)
            snap["generated_at"]=1792000200
            with self.assertRaises(ValueError):
                record_private_decision(file,snap,"pilot-V31",now=1792000100)

    def test_refuse_actual_stock_db_even_when_filename_is_misleading(self):
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/"experimental.db"
            with sqlite3.connect(file) as con:
                con.execute("CREATE TABLE stock_history(timestamp integer)")
            before=file.read_bytes()
            with self.assertRaises(ValueError):
                record_private_decision(file,private_snapshot(),"pilot-V31",now=1792000100)
            self.assertEqual(file.read_bytes(),before)

    def test_reject_active_routing_wrong_schema_backdated_claims_and_inconsistent_result(self):
        snap=private_snapshot()
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/"private.db"
            snap["default_live_routing"]="CHALLENGER"
            with self.assertRaises(ValueError):
                record_private_decision(target,snap,"pilot-V31")
            snap["default_live_routing"]="UNCHANGED"
            snap["chance_calibrated"]=True
            with self.assertRaises(ValueError):
                record_private_decision(target,snap,"pilot-V31")
            snap["chance_calibrated"]=False
            snap["champion_executed"]=False
            with self.assertRaises(ValueError):
                record_private_decision(target,snap,"pilot-V31")
            snap["champion_executed"]=True
            with self.assertRaises(ValueError):
                record_private_decision(target,snap,"bad experiment id")

if __name__=="__main__":
    unittest.main()
