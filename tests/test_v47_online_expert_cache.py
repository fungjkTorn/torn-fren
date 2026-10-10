"""V47 persisted Monkey/Chamois score ledger: resume, no lookahead, no writes."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research import v47_online_expert_cache as m


NOW=1800000000
KEY="arg:Monkey Plushie"


class ResolvedExpertCacheTests(unittest.TestCase):
    def test_frozen_beta_scoring_with_ties_and_unresolved(self):
        anchor=NOW-50000
        data={
            (anchor,0):(1,NOW-200),
            (anchor,1):(0,NOW-200),
            (anchor,2):(1,None),
        }
        chosen=m.score_experts(data,[anchor],NOW,2,count=3)
        self.assertEqual(chosen["expert_index"],0)
        self.assertEqual(chosen["posterior_score"],.6)
        self.assertEqual(chosen["resolved_count"],1)

    def test_missing_expert_must_abstain(self):
        self.assertIsNone(m.score_experts({(100,0):(1,200)},[100],300,2,count=2))

    def test_causality_skips_future_resolutions(self):
        anchor=NOW-60000
        d={(anchor,0):(1,NOW+1),(anchor,1):(0,NOW-1)}
        s=m.score_experts(d,[anchor],NOW,2,count=2)
        self.assertEqual(s["expert_index"],1)
        self.assertEqual(s["resolved_count"],1)

    def test_gap_revisions_invalidate_private_ledger(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"history.db"
            side=sqlite3.connect(Path(folder)/"private.db")
            try:
                with sqlite3.connect(path) as raw:
                    raw.execute("CREATE TABLE stock_history (id INTEGER PRIMARY KEY,timestamp INTEGER,country TEXT,item_name TEXT,quantity INTEGER)")
                    raw.execute("INSERT INTO stock_history VALUES (1,100,'arg','Monkey Plushie',45)")
                src=sqlite3.connect(path)
                try:
                    m.initialize(side)
                    m.update_cache_source(side,src,KEY,"arg","Monkey Plushie","h1")
                    side.execute("""INSERT INTO expert_resolutions VALUES(?,?,?,?,?,?,?,?)""",
                                 (KEY,100,0,"RESOLVED_EXPERT_DECISION",1,200,150,190))
                    side.commit()
                    self.assertFalse(m.update_cache_source(
                        side,src,KEY,"arg","Monkey Plushie","h1"))
                    self.assertEqual(side.execute("SELECT COUNT(*) FROM expert_resolutions").fetchone()[0],1)
                    self.assertTrue(m.update_cache_source(
                        side,src,KEY,"arg","Monkey Plushie","h2"))
                    self.assertEqual(side.execute("SELECT COUNT(*) FROM expert_resolutions").fetchone()[0],0)
                finally:
                    src.close()
            finally:
                side.close()

    def test_backdated_stock_inserts_invalidate_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"history.db"
            side=sqlite3.connect(Path(folder)/"private.db")
            try:
                with sqlite3.connect(path) as raw:
                    raw.execute("CREATE TABLE stock_history (id INTEGER PRIMARY KEY,timestamp INTEGER,country TEXT,item_name TEXT,quantity INTEGER)")
                    raw.execute("INSERT INTO stock_history VALUES (1,100,'arg','Monkey Plushie',45)")
                src=sqlite3.connect(path)
                try:
                    m.initialize(side)
                    m.update_cache_source(side,src,KEY,"arg","Monkey Plushie","h1")
                    side.execute("""INSERT INTO expert_resolutions VALUES(?,?,?,?,?,?,?,?)""",
                                 (KEY,100,0,"RESOLVED_EXPERT_DECISION",1,200,150,190))
                    side.commit()
                    src.execute("INSERT INTO stock_history VALUES(2,150,'arg','Monkey Plushie',0)")
                    src.commit()
                    self.assertTrue(m.update_cache_source(
                        side,src,KEY,"arg","Monkey Plushie","h1"))
                    self.assertEqual(side.execute("SELECT COUNT(*) FROM expert_resolutions").fetchone()[0],0)
                finally:
                    src.close()
            finally:
                side.close()

    def test_resume_and_publish_only_after_complete_bank(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"history.db"
            cache=Path(folder)/"research_cache.db"
            with sqlite3.connect(path) as src:
                src.execute("""CREATE TABLE stock_history (
                    id INTEGER PRIMARY KEY,timestamp INTEGER,country TEXT,
                    item_name TEXT,quantity INTEGER,source TEXT)""")
                src.execute("""CREATE TABLE collection_gaps (
                    id INTEGER PRIMARY KEY,start_timestamp INTEGER,end_timestamp INTEGER)""")
                src.executemany("""INSERT INTO stock_history VALUES(?,?,?,?,?,?)""",[
                    (1,NOW-11*m.DAY,"arg","Monkey Plushie",45,"test"),
                    (2,NOW-600,"arg","Monkey Plushie",0,"test"),
                ])
            anchor=NOW-45000
            class StubPlanner:
                def __init__(self,*args,**kwargs):
                    pass
                def plan(self,query):
                    return (query+600,.6,{})
            def historical(planner,timeline,start,travel):
                return {"status":"RESOLVED_EXPERT_DECISION",
                        "success":1,"resolved_at":NOW-100,
                        "departure":start+300,"arrival":start+300+travel}
            with patch.object(m,"inspect_live_source",return_value={"status":"FRESH"}), \
                 patch.object(m,"eligible_starts",return_value=[anchor]), \
                 patch.object(m,"FastTemplatePlanner",StubPlanner), \
                 patch.object(m,"simulate_one",side_effect=historical):
                first=m.run(path,cache,"monkey",NOW,max_decisions=12)
                self.assertEqual(first["status"],"BUILDING_RESOLVED_EXPERT_CACHE")
                self.assertEqual(first["cached_decisions"],12)
                second=m.run(path,cache,"monkey",NOW,max_decisions=12)
                self.assertEqual(second["status"],"RESEARCH_PROPOSAL_ONLY")
                self.assertEqual(second["cached_decisions"],24)
                self.assertEqual(second["executed_decisions"],12)
                self.assertEqual(second["recommended_departure_timestamp"],
                                 (NOW//m.STEP)*m.STEP+600)
                self.assertEqual(second["chosen_expert_index"],0)
                third=m.run(path,cache,"monkey",NOW,max_decisions=1)
                self.assertEqual(third["executed_decisions"],0)
                self.assertEqual(third["status"],"RESEARCH_PROPOSAL_ONLY")
            with sqlite3.connect(cache) as check:
                self.assertEqual(check.execute("SELECT COUNT(*) FROM expert_resolutions").fetchone()[0],24)


if __name__=="__main__":
    unittest.main()
