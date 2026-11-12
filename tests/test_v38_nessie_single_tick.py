"""Causal Nessie single-tick specialist and cheap target-only context tests."""
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.v38_nessie_single_tick import predict,COUNTRY,ITEM,CONFIG,TRAVEL
from research.plushie_champions.common import ResearchContext

BEGIN=1790000000


class NessieSingleTickTests(unittest.TestCase):
    def synthetic_db(self,folder,*,future=False):
        path=Path(folder)/"stock.db"
        now=BEGIN+1399*300+60
        with sqlite3.connect(path) as c:
            c.executescript("""
                CREATE TABLE stock_history(timestamp INTEGER,country TEXT,item_name TEXT,
                    quantity INTEGER,source TEXT);
                CREATE TABLE poll_heartbeats(timestamp INTEGER,success INTEGER,mode TEXT);
                CREATE TABLE collection_gaps(start_timestamp INTEGER,end_timestamp INTEGER,reason TEXT);
            """)
            c.executemany("INSERT INTO stock_history VALUES (?,?,?,?,?)",[
                (BEGIN+j*300,"uni","Nessie Plushie",120 if j%36<24 else 0,"synthetic")
                for j in range(1400)
            ])
            if future:
                c.execute("INSERT INTO stock_history VALUES (?,?,?,?,?)",
                          (now+60,"uni","Nessie Plushie",0,"synthetic"))
            c.execute("INSERT INTO poll_heartbeats VALUES (?,?,?)",
                      (now-20,1,"poll-cycle"))
        return path,now

    def test_source_config_unchanged(self):
        self.assertEqual(CONFIG,{"lags":(1,),"lookback":7200,
                                 "shift_range":3600,"minfit":0.5})

    def test_actual_original_template_is_causal_readonly_and_single_item(self):
        with tempfile.TemporaryDirectory() as folder:
            path,now=self.synthetic_db(folder)
            before=hashlib.sha256(path.read_bytes()).hexdigest()
            # Directly assert no all-ten-plushie historical ResearchContext
            # construction or expensive cross-item training is attempted.
            with patch.object(ResearchContext,"build",
                              side_effect=AssertionError("full replay not allowed")):
                r=predict(path,COUNTRY,ITEM,now)
            self.assertEqual(r["status"],"RESEARCH_PROPOSAL_ONLY",r)
            self.assertEqual(r["model_generation"],"recent_phase_template")
            self.assertEqual(r["key"],"uni:Nessie Plushie")
            self.assertEqual(r["recommended_arrival_timestamp"]-
                             r["recommended_departure_timestamp"],TRAVEL)
            self.assertGreaterEqual(r["recommended_departure_timestamp"],now)
            self.assertLessEqual(r["recommended_departure_timestamp"],now+28800)
            self.assertFalse(r["probability_calibrated"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)

    def test_fail_closed_non_nessie_and_future_data(self):
        self.assertEqual(predict("/not/a/db","uni","Heather",BEGIN)["status"],
                         "NOT_APPROVED_NESSIE_TEMPLATE")
        with tempfile.TemporaryDirectory() as folder:
            path,now=self.synthetic_db(folder,future=True)
            r=predict(path,COUNTRY,ITEM,now)
            self.assertEqual(r["status"],"FUTURE_RECORDS_PRESENT")


if __name__=="__main__":unittest.main()
