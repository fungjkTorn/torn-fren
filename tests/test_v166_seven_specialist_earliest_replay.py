import sqlite3
import tempfile
import unittest
from pathlib import Path

from research.v166_seven_specialist_earliest_replay import (
    CausalMirror, MODEL_FREEZE_EPOCH, SEVEN
)


def make_source(path):
    con=sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE stock_history(
      id INTEGER PRIMARY KEY,timestamp INTEGER,country TEXT,
      item_name TEXT,quantity INTEGER,source TEXT);
    CREATE TABLE poll_heartbeats(
      id INTEGER PRIMARY KEY,timestamp INTEGER,mode TEXT,success INTEGER);
    CREATE TABLE collection_gaps(
      id INTEGER PRIMARY KEY,start_timestamp INTEGER,end_timestamp INTEGER,reason TEXT);
    """)
    con.executemany("INSERT INTO stock_history VALUES(?,?,?,?,?,?)",[
        (1,1000,"uni","Nessie Plushie",0,"p"),
        (2,1200,"uni","Nessie Plushie",40,"p"),
        (3,1600,"uni","Nessie Plushie",0,"p"),
    ])
    con.executemany("INSERT INTO poll_heartbeats VALUES(?,?,?,?)",[
        (1,1000,"poll-cycle",1),(2,1200,"poll-cycle",1),(3,1600,"poll-cycle",1)
    ])
    con.execute("INSERT INTO collection_gaps VALUES(1,1100,1500,'x')")
    con.commit();con.close()


class V166MirrorTests(unittest.TestCase):
    def test_roster_is_exact_seven(self):
        self.assertEqual(7,len(SEVEN))
        self.assertIn("arg:Monkey Plushie",SEVEN)
        self.assertIn("uni:Red Fox Plushie",SEVEN)

    def test_freeze_epoch_is_after_oct8_release(self):
        self.assertGreaterEqual(MODEL_FREEZE_EPOCH,1791497135)

    def test_mirror_never_exposes_future_rows(self):
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/"source.sqlite"; dst=Path(td)/"mirror.sqlite"
            make_source(src)
            m=CausalMirror(src,dst,1200)
            con=sqlite3.connect(dst)
            self.assertEqual(1200,con.execute("SELECT MAX(timestamp) FROM stock_history").fetchone()[0])
            self.assertEqual(1200,con.execute("SELECT MAX(timestamp) FROM poll_heartbeats").fetchone()[0])
            # gap started but had not causally closed at 1200
            self.assertIsNone(con.execute("SELECT end_timestamp FROM collection_gaps").fetchone()[0])
            con.close()

            m.advance(1600)
            con=sqlite3.connect(dst)
            self.assertEqual(1600,con.execute("SELECT MAX(timestamp) FROM stock_history").fetchone()[0])
            self.assertEqual(1500,con.execute("SELECT end_timestamp FROM collection_gaps").fetchone()[0])
            con.close()

    def test_mirror_rejects_clock_reversal(self):
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/"source.sqlite"; dst=Path(td)/"mirror.sqlite"
            make_source(src)
            m=CausalMirror(src,dst,1200)
            with self.assertRaises(ValueError):
                m.advance(1100)

    def test_mirror_accepts_source_without_surrogate_ids(self):
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/'source-noids.sqlite'; dst=Path(td)/'mirror.sqlite'
            con=sqlite3.connect(src)
            con.executescript("""
            CREATE TABLE stock_history(
              timestamp INTEGER,country TEXT,item_name TEXT,
              quantity INTEGER,source TEXT);
            CREATE TABLE poll_heartbeats(
              timestamp INTEGER,mode TEXT,success INTEGER);
            CREATE TABLE collection_gaps(
              start_timestamp INTEGER,end_timestamp INTEGER);
            """)
            con.execute(
                'INSERT INTO stock_history VALUES(?,?,?,?,?)',
                (1000,'uni','Nessie Plushie',0,'p'))
            con.execute(
                'INSERT INTO poll_heartbeats VALUES(?,?,?)',
                (1000,'poll-cycle',1))
            con.execute(
                'INSERT INTO collection_gaps VALUES(?,?)',
                (900,1100))
            con.commit();con.close()

            CausalMirror(src,dst,1000)
            con=sqlite3.connect(dst)
            self.assertEqual(
                1000,
                con.execute('SELECT MAX(timestamp) FROM stock_history').fetchone()[0])
            self.assertEqual(
                1000,
                con.execute('SELECT MAX(timestamp) FROM poll_heartbeats').fetchone()[0])
            self.assertEqual(
                'historical',
                con.execute('SELECT reason FROM collection_gaps').fetchone()[0])
            con.close()


if __name__=="__main__":
    unittest.main()
