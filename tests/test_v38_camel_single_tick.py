"""Original Camel 24-template selector executes bounded causal read-only inference."""
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.v38_camel_single_tick import predict,EXPERTS
from research.plushie_champions.common import ResearchContext,TRAVEL_SECONDS

BEGIN=1790000000


class V38CamelTests(unittest.TestCase):
    def test_exact_twenty_four_experts_and_approval(self):
        self.assertEqual(len(EXPERTS),24)
        self.assertEqual(len(set(EXPERTS)),24)
        self.assertEqual(predict("/no/db","uae","Tribulus Omanense",BEGIN)["status"],
                         "NOT_APPROVED_CAMEL_SELECTOR")

    def test_source_pinned_selector_without_full_historical_context(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"stock.db"
            now=BEGIN+1399*300+60
            with sqlite3.connect(p) as c:
                c.executescript("""
                    CREATE TABLE stock_history(timestamp INTEGER,country TEXT,
                        item_name TEXT,quantity INTEGER,source TEXT);
                    CREATE TABLE poll_heartbeats(timestamp INTEGER,success INTEGER,mode TEXT);
                    CREATE TABLE collection_gaps(start_timestamp INTEGER,end_timestamp INTEGER,reason TEXT);
                """)
                c.executemany("INSERT INTO stock_history VALUES (?,?,?,?,?)",[
                    (BEGIN+j*300,"uae","Camel Plushie",120 if j%36<24 else 0,"synthetic")
                    for j in range(1400)
                ])
                c.execute("INSERT INTO poll_heartbeats VALUES (?,?,?)",
                          (now-20,1,"poll-cycle"))
            before=hashlib.sha256(p.read_bytes()).hexdigest()
            with patch.object(ResearchContext,"build",
                              side_effect=AssertionError("full replay not allowed")):
                r=predict(p,"uae","Camel Plushie",now)
            self.assertEqual(r["status"],"RESEARCH_PROPOSAL_ONLY",r)
            self.assertEqual(r["model_generation"],"template_probability_selector")
            self.assertEqual(r["recommended_arrival_timestamp"]-
                             r["recommended_departure_timestamp"],TRAVEL_SECONDS["uae"])
            self.assertGreaterEqual(r["recommended_departure_timestamp"],now)
            self.assertLessEqual(r["recommended_departure_timestamp"],now+28800)
            self.assertFalse(r["probability_calibrated"])
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),before)


if __name__=="__main__":unittest.main()
