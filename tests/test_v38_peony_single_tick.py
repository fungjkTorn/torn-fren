"""Ensure original V20 traj12 Peony engine returns causal bounded proposals."""
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from research.v38_peony_single_tick import predict,CONFIG
from services.plushie_flower_dynamic_planner_v20 import TRAVEL_SECONDS,configs

BEGIN=1790000000


class V38PeonyTests(unittest.TestCase):
    def test_source_pinned_config_and_fail_closed(self):
        self.assertEqual(CONFIG,"traj12")
        self.assertIn(CONFIG,[x.name for x in configs()])
        self.assertEqual(predict("/none","chi","Panda Plushie",BEGIN)["status"],
                         "NOT_APPROVED_PEONY_V20")

    def test_real_original_trajectory_model(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"stock.db"
            now=BEGIN+1399*300+60
            with sqlite3.connect(p) as con:
                con.executescript("""
                    CREATE TABLE stock_history(timestamp INTEGER,country TEXT,
                        item_name TEXT,quantity INTEGER,source TEXT);
                    CREATE TABLE poll_heartbeats(timestamp INTEGER,success INTEGER,mode TEXT);
                    CREATE TABLE collection_gaps(start_timestamp INTEGER,end_timestamp INTEGER,reason TEXT);
                """)
                con.executemany("INSERT INTO stock_history VALUES (?,?,?,?,?)",[
                    (BEGIN+j*300,"chi","Peony",120 if j%36<24 else 0,"synthetic")
                    for j in range(1400)
                ])
                con.execute("INSERT INTO poll_heartbeats VALUES (?,?,?)",
                            (now-20,1,"poll-cycle"))
            before=hashlib.sha256(p.read_bytes()).hexdigest()
            r=predict(p,"chi","Peony",now)
            self.assertEqual(r["status"],"RESEARCH_PROPOSAL_ONLY",r)
            self.assertEqual(r["model_generation"],"V20")
            self.assertEqual(r["model_config"],"traj12")
            self.assertGreaterEqual(r["recommended_departure_timestamp"],now)
            self.assertLessEqual(r["recommended_departure_timestamp"],now+28800)
            self.assertEqual(r["recommended_arrival_timestamp"]-
                             r["recommended_departure_timestamp"],TRAVEL_SECONDS["chi"])
            self.assertFalse(r["probability_calibrated"])
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),before)


if __name__=="__main__":unittest.main()
