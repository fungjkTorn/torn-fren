"""Run the actual native v18/v19 planners against an isolated synthetic SQLite.

This is a code-execution smoke test. Synthetic success is NOT model accuracy.
"""
from __future__ import annotations
from dataclasses import asdict
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research.v30_native_parity_probe import _native_candidate, source_provenance


def make_fixture(path):
    base=1790000000
    with sqlite3.connect(path) as con:
        con.executescript("""
            CREATE TABLE stock_history (
                timestamp INTEGER, country TEXT, item_name TEXT,
                quantity INTEGER, source TEXT);
            CREATE TABLE collection_gaps (
                start_timestamp INTEGER, end_timestamp INTEGER, reason TEXT);
            CREATE TABLE poll_heartbeats (
                timestamp INTEGER, success INTEGER, mode TEXT);
        """)
        rows=[]
        for j in range(31*36+1):
            sec=j*300
            phase=sec % 10800
            q=0 if j==0 else (120 if phase<7200 else 0)
            rows.append((base+sec,"mex","Jaguar Plushie",q,"synthetic"))
        con.executemany(
            "INSERT INTO stock_history VALUES (?,?,?,?,?)",rows)
    return base


class NativeSourceSmokeTests(unittest.TestCase):
    def test_native_v18_and_v19_run_on_archived_readonly_synthetic(self):
        from services import plushie_flower_dynamic_planner_v18 as v18
        from services import plushie_flower_dynamic_planner_v19 as v19
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/"source.db"
            base=make_fixture(db)
            source_hash=hashlib.sha256(db.read_bytes()).hexdigest()
            self.assertTrue(source_provenance(
                {"settings":{"db_sha256":source_hash}},source_hash
            )["same_snapshot_proven"])
            for version,model in (("v19",v18),("v20",v19),("v21",v19)):
                with self.subTest(version=version):
                    start=base+25*10800
                    saved={"status":"complete",
                           "selected_on_training":{"config":asdict(model.configs()[0])},
                           "holdout_rows":[{"start":start,
                                            "departure":start+300,
                                            "success":False}],
                           "schema":"plushie-flower-dynamic-planner-v18.1-item-v1"
                                    if version=="v19" else
                                    "plushie-flower-dynamic-planner-v19-item-v1"}
                    master={"results":{"mex:Jaguar Plushie":saved},
                            "settings":{"options":{"max_wait":43200,
                                             "departure_grid":900,
                                             "replan_step":900}}}
                    out=_native_candidate(db,version,"mex:Jaguar Plushie",master,saved,1)
                    self.assertEqual(out["n"],1)
                    self.assertGreater(out["cycles_rebuilt"],12)
                    self.assertGreater(out["points_rebuilt"],60)
                    self.assertEqual(out["engine_family"],
                         "services.plushie_flower_dynamic_planner_v18"
                         if version=="v19" else
                         "services.plushie_flower_dynamic_planner_v19")
                    self.assertIsNotNone(out["rows"][0]["replayed_departure"])
                    self.assertTrue(db.exists())
                    # Native replay could not write to the frozen source.
                    self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(),source_hash)


if __name__=="__main__":
    unittest.main()
