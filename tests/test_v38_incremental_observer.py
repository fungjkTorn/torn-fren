"""Delta/feature-cache unit tests, isolated from live collector."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research.v38_incremental_observer import observe
from research.v38_feature_cache import get, put, prune_old_slots
from research.v38_prediction_store import open_writer


class IncrementalObserverTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/"stock.db"
        self.side=Path(self.tmp.name)/"research.db"
        with sqlite3.connect(self.db) as c:
            c.execute("""CREATE TABLE stock_history(
                id INTEGER PRIMARY KEY,timestamp INTEGER,country TEXT,
                item_name TEXT,quantity INTEGER)""")
            c.execute("""CREATE TABLE collection_gaps(
                id INTEGER PRIMARY KEY,start_timestamp INTEGER)""")
            c.executemany("INSERT INTO stock_history VALUES(?,?,?,?,?)",[
                (1,100,"uni","Heather",0),(2,120,"can","Crocus",30),
                (3,140,"uni","Heather",50)])
        self.con=open_writer(self.side)
        self.addCleanup(self.con.close)

    def test_capped_bootstrap_and_versioned_cache(self):
        first=observe(self.db,self.con,max_rows=2)
        self.assertEqual(first["processed"],2)
        self.assertFalse(first["caught_up"])
        self.assertFalse(put(self.con,key="uni:Heather",config="dyn3",
                             schema="v1",slot=0,features={"a":1}))
        second=observe(self.db,self.con,max_rows=2)
        self.assertTrue(second["caught_up"])
        self.assertEqual(second["affected_keys"],["uni:Heather"])
        self.assertTrue(put(self.con,key="uni:Heather",config="dyn3",
                            schema="v1",slot=300,features={"a":1}))
        self.assertEqual(get(self.con,key="uni:Heather",config="dyn3",
                             schema="v1",slot=300),{"a":1})
        self.assertIsNone(get(self.con,key="uni:Heather",config="dyn2",
                              schema="v1",slot=300))
        self.assertIsNone(get(self.con,key="uni:Heather",config="dyn3",
                              schema="v2",slot=300))
        self.assertIsNone(get(self.con,key="uni:Heather",config="dyn3",
                              schema="v1",slot=600))
        self.assertEqual(prune_old_slots(self.con,301),1)

    def test_new_stock_and_gap_change_invalidate(self):
        observe(self.db,self.con)
        self.assertTrue(put(self.con,key="uni:Heather",config="dyn3",
                            schema="v1",slot=300,features={"old":True}))
        with sqlite3.connect(self.db) as c:
            c.execute("INSERT INTO stock_history VALUES(4,160,'uni','Heather',0)")
        d=observe(self.db,self.con)
        self.assertEqual(d["affected_keys"],["uni:Heather"])
        self.assertIsNone(get(self.con,key="uni:Heather",config="dyn3",
                              schema="v1",slot=300))
        self.assertTrue(put(self.con,key="uni:Heather",config="dyn3",
                            schema="v1",slot=300,features={"new":True}))
        with sqlite3.connect(self.db) as c:
            c.execute("INSERT INTO collection_gaps VALUES(1,150)")
        observe(self.db,self.con)
        self.assertIsNone(get(self.con,key="uni:Heather",config="dyn3",
                              schema="v1",slot=300))

    def test_collector_not_written_and_reset_detected(self):
        observe(self.db,self.con)
        with sqlite3.connect(self.db) as c:
            c.execute("DELETE FROM stock_history WHERE id=3")
        status=observe(self.db,self.con)
        self.assertTrue(status["reset"])
        self.assertEqual(status["last_id"],2)
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM stock_history").fetchone()[0],2)

    def test_unbounded_scan_denied(self):
        with self.assertRaises(ValueError):
            observe(self.db,self.con,max_rows=50001)


if __name__ == "__main__":
    unittest.main()
