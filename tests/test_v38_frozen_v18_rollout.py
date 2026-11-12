"""V38 model-adapter contracts: exact provenance, causal source, no DB writes."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.v38_v18_single_tick import V18_APPROVED, predict
from services.private_v18_champion_worker_v35 import (
    FROZEN_V18_PILOT, single_tick as v35_tick,
)

ROSTER = Path(__file__).resolve().parents[1] / "research" / "v38_roster.json"
BEGIN = 1790000000


class V38FrozenAdapterTests(unittest.TestCase):
    def test_22_item_roster_and_10_pinned_v18_winners(self):
        d = json.loads(ROSTER.read_text(encoding="utf-8"))
        self.assertEqual(len(d["items"]), 22)
        v18 = {
            key: rec["config_name"]
            for key, rec in d["items"].items()
            if rec["model_family"] == "V18"
        }
        self.assertEqual(v18, V18_APPROVED)
        for key in V18_APPROVED:
            self.assertEqual(d["items"][key]["source_path"],
                             "services/plushie_flower_dynamic_planner_v18.py")
        self.assertEqual(d["policy"]["max_departure_wait_seconds"], 28800)
        self.assertEqual(d["policy"]["replan_seconds"], 300)
        self.assertTrue(d["policy"]["live_public_routing_unchanged"])

    def test_old_v35_default_allowlist_remains_strict(self):
        self.assertEqual(FROZEN_V18_PILOT,
                         {"uni:Heather": "dyn3", "can:Wolverine Plushie": "dyn8"})
        self.assertEqual(v35_tick("/not/a/db", "arg", "Ceibo Flower",
                                   "dyn3", BEGIN)["status"],
                         "NOT_APPROVED_FROZEN_V18_PILOT")
        self.assertEqual(predict("/not/a/db", "uni", "Nessie Plushie",
                                 BEGIN)["status"],
                         "NOT_APPROVED_FROZEN_V18_V38")

    def test_v38_uses_exact_frozen_config_and_original_engine(self):
        for key,config in V18_APPROVED.items():
            country,item=key.split(":",1)
            with self.subTest(key=key),patch(
                "research.v38_v18_single_tick.frozen_v18_tick",
                return_value={"status":"RESEARCH_PROPOSAL_ONLY"}
            ) as f:
                out=predict("/not/a/db",country,item,BEGIN)
                self.assertEqual(out["status"],"RESEARCH_PROPOSAL_ONLY")
                f.assert_called_once_with("/not/a/db",country,item,config,BEGIN,
                    approved_configs=V18_APPROVED)

    def test_original_live_inference_all_ten_on_synthetic_readonly_db(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"stock.db"
            now=BEGIN+1399*300+60
            with sqlite3.connect(path) as db:
                db.executescript("""
                    CREATE TABLE stock_history(
                        timestamp INTEGER,country TEXT,item_name TEXT,
                        quantity INTEGER,source TEXT);
                    CREATE TABLE poll_heartbeats(
                        timestamp INTEGER,success INTEGER,mode TEXT);
                    CREATE TABLE collection_gaps(
                        start_timestamp INTEGER,end_timestamp INTEGER,reason TEXT);
                """)
                for key in V18_APPROVED:
                    country,item=key.split(":",1)
                    db.executemany("INSERT INTO stock_history VALUES (?,?,?,?,?)",[
                        (BEGIN+j*300,country,item,120 if j%36<24 else 0,"synthetic")
                        for j in range(1400)
                    ])
                db.execute("INSERT INTO poll_heartbeats VALUES (?,?,?)",
                           (now-20,1,"poll-cycle"))
            before=hashlib.sha256(path.read_bytes()).hexdigest()
            for key,config in V18_APPROVED.items():
                country,item=key.split(":",1)
                with self.subTest(key=key):
                    r=predict(path,country,item,now)
                    self.assertEqual(r.get("status"),"RESEARCH_PROPOSAL_ONLY",r)
                    self.assertEqual(r["model_generation"],"V18")
                    self.assertEqual(r["model_config"],config)
                    self.assertEqual(r["key"],key)
                    self.assertGreaterEqual(r["recommended_departure_timestamp"],now)
                    self.assertLessEqual(r["recommended_departure_timestamp"],now+28800)
                    self.assertEqual(r["recommended_arrival_timestamp"]-
                                     r["recommended_departure_timestamp"],
                                     __import__("services.plushie_flower_dynamic_planner_v18",
                                                fromlist=["TRAVEL_SECONDS"]).TRAVEL_SECONDS[country])
                    self.assertEqual(r["replan_step_seconds"],300)
                    self.assertFalse(r["probability_calibrated"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)

    def test_refuses_future_observations_on_readonly_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"stock.db"
            now=BEGIN+1399*300+60
            with sqlite3.connect(path) as db:
                db.executescript("""
                    CREATE TABLE stock_history(
                        timestamp INTEGER,country TEXT,item_name TEXT,
                        quantity INTEGER,source TEXT);
                    CREATE TABLE poll_heartbeats(
                        timestamp INTEGER,success INTEGER,mode TEXT);
                    CREATE TABLE collection_gaps(
                        start_timestamp INTEGER,end_timestamp INTEGER,reason TEXT);
                """)
                db.execute("INSERT INTO stock_history VALUES (?,?,?,?,?)",
                           (now+60,"uni","Heather",0,"synthetic"))
                db.execute("INSERT INTO poll_heartbeats VALUES (?,?,?)",
                           (now-20,1,"poll-cycle"))
            r=predict(path,"uni","Heather",now)
            self.assertEqual(r["status"],"FUTURE_RECORDS_PRESENT")


if __name__=="__main__":
    unittest.main()
