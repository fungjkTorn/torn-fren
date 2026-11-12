import sqlite3
import tempfile
import unittest
from pathlib import Path
from scripts.check_v169_source_coverage import inspect


class SourceCoverageTests(unittest.TestCase):
    def test_sanitized_roster_24_and_missing_sou_detected_without_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"source.db"
            with sqlite3.connect(p) as db:
                db.executescript("""
                CREATE TABLE stock_history(timestamp INTEGER,quantity INTEGER,source TEXT,
                                           country TEXT,item_name TEXT);
                CREATE TABLE poll_heartbeats(timestamp INTEGER,mode TEXT,success INTEGER);
                CREATE TABLE research_metadata(key TEXT,value TEXT);
                INSERT INTO poll_heartbeats VALUES(123456,'poll-cycle',1);
                INSERT INTO research_metadata VALUES('sanitized_stock_only','true');
                INSERT INTO research_metadata VALUES('roster_size','24');
                INSERT INTO stock_history VALUES(123000,0,'yata','sou','Lion Plushie');
                """)
            before=p.read_bytes()
            r=inspect(p)
            self.assertEqual(r["status"],"MISSING_SOUTH_AFRICA_XANAX_HISTORY")
            self.assertEqual(r["source_roster_size"],"24")
            self.assertEqual(p.read_bytes(),before)
            with sqlite3.connect(p) as db:
                db.execute("INSERT INTO stock_history VALUES(123450,2000,'yata','sou','Xanax')")
            got=inspect(p)
            self.assertEqual(got["status"],"SOUTH_AFRICA_HISTORY_PRESENT")
            self.assertEqual(got["stock_change_rows"],1)


if __name__=="__main__":
    unittest.main()
