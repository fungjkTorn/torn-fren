import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research"/"plushie_champions"))
from locked_replay import cohort, TARGETS, _row, _summarize
from common import ResearchContext, PLUSHIES, MAX_WAIT, TRAVEL_SECONDS


class LockedReplayTests(unittest.TestCase):
    def test_targets(self):
        self.assertEqual(len(TARGETS),7)
        self.assertEqual(len(set(TARGETS.values())),7)

    def test_missing_recommendations_are_failures(self):
        r=_summarize([{"start":0,"departure":None,"arrival":None,"success":False,"recommended":False},
                     {"start":1800,"departure":1800,"arrival":3000,"success":True,"recommended":True}])
        self.assertEqual((r["hits"],r["starts"],r["coverage"],r["all_start_success"]),
                         (1,2,.5,.5))

    def test_fixed_cutoff_never_retests_older_starts(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"history.db"
            with sqlite3.connect(path) as con:
                con.executescript("""
                CREATE TABLE stock_history
                   (timestamp INTEGER, country TEXT, item_name TEXT, quantity INTEGER, source TEXT);
                CREATE TABLE collection_gaps(start_timestamp INTEGER,end_timestamp INTEGER);
                """)
                first=1790000000
                data=[(first+j*3600,country,item,100 if j%6<3 else 0,"fake")
                     for country,item in PLUSHIES for j in range(24*15)]
                con.executemany("INSERT INTO stock_history VALUES (?,?,?,?,?)",data)
            ctx=ResearchContext.build(path)
            try:
                cutoff=first+9*86400
                s=cohort(ctx,"uni","Nessie Plushie",cutoff,max_starts=8)
                self.assertTrue(s)
                self.assertTrue(all(x>=cutoff for x in s))
                self.assertTrue(all(x+MAX_WAIT+TRAVEL_SECONDS["uni"] <=
                                    ctx.timelines[("uni","Nessie Plushie")].ts[-1] for x in s))
            finally:
                ctx.con.close()


if __name__=="__main__":
    unittest.main()
