"""Source-pinned original V19 live adapter validation (never V20 fallback)."""
from __future__ import annotations
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research.v38_v19_single_tick import V19_APPROVED, predict
from services.plushie_flower_dynamic_planner_v19 import TRAVEL_SECONDS

ROSTER=Path(__file__).resolve().parents[1]/"research"/"v38_roster.json"
BEGIN=1790000000


class V38V19Tests(unittest.TestCase):
    def test_exact_pinned_configurations_match_roster(self):
        items=json.loads(ROSTER.read_text())["items"]
        expected={k:v["config_name"] for k,v in items.items()
                  if v["model_family"]=="V19"}
        self.assertEqual(expected,V19_APPROVED)
        self.assertEqual(len(V19_APPROVED),3)
        self.assertEqual(predict("/not/a/db","chi","Peony",BEGIN)["status"],
                         "NOT_APPROVED_FROZEN_V19_V38")

    def test_three_v19_champions_generate_original_engine_live_proposals(self):
        with tempfile.TemporaryDirectory() as directory:
            dbpath=Path(directory)/"stock.db"
            now=BEGIN+1399*300+60
            with sqlite3.connect(dbpath) as con:
                con.executescript("""
                CREATE TABLE stock_history(timestamp INTEGER,country TEXT,
                    item_name TEXT,quantity INTEGER,source TEXT);
                CREATE TABLE poll_heartbeats(timestamp INTEGER,success INTEGER,mode TEXT);
                CREATE TABLE collection_gaps(start_timestamp INTEGER,end_timestamp INTEGER,reason TEXT);
                """)
                for key in V19_APPROVED:
                    country,item=key.split(":",1)
                    con.executemany("INSERT INTO stock_history VALUES (?,?,?,?,?)",[
                        (BEGIN+j*300,country,item,120 if j%36<24 else 0,"synthetic")
                        for j in range(1400)
                    ])
                con.execute("INSERT INTO poll_heartbeats VALUES (?,?,?)",
                            (now-20,1,"poll-cycle"))
            before=hashlib.sha256(dbpath.read_bytes()).hexdigest()
            for key,conf in V19_APPROVED.items():
                country,item=key.split(":",1)
                with self.subTest(key=key):
                    r=predict(dbpath,country,item,now)
                    self.assertEqual(r.get("status"),"RESEARCH_PROPOSAL_ONLY",r)
                    self.assertEqual(r["model_generation"],"V19")
                    self.assertEqual(r["model_config"],conf)
                    self.assertEqual(r["key"],key)
                    self.assertGreaterEqual(r["recommended_departure_timestamp"],now)
                    self.assertLessEqual(r["recommended_departure_timestamp"],now+28800)
                    self.assertEqual(r["recommended_arrival_timestamp"]-
                                     r["recommended_departure_timestamp"],
                                     TRAVEL_SECONDS[country])
                    self.assertEqual(r["replan_step_seconds"],300)
                    self.assertFalse(r["probability_calibrated"])
            self.assertEqual(hashlib.sha256(dbpath.read_bytes()).hexdigest(),before)


if __name__=="__main__":unittest.main()
