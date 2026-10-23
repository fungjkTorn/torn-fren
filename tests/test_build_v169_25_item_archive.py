"""Research-only source extension never mutates collector or 24-item archive."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from deploy.research_runner.build_v169_25_item_archive import build,OUT_NAME


class SouthAfrica25ArchiveTests(unittest.TestCase):
    def setup_sources(self,root,include_sou=True):
        base=root/"base.db";collector=root/"collector.db"
        with sqlite3.connect(base) as db:
            db.executescript("""
                CREATE TABLE stock_history(
                    id INTEGER PRIMARY KEY,
                    timestamp INTEGER,quantity INTEGER,source TEXT,
                    country TEXT,item_name TEXT
                );
                CREATE TABLE poll_heartbeats(timestamp INTEGER,mode TEXT,success INTEGER);
                CREATE TABLE research_metadata(key TEXT PRIMARY KEY,value TEXT);
                INSERT INTO stock_history(timestamp,quantity,source,country,item_name)
                VALUES(1000000,50,'yata','uni','Nessie Plushie');
                INSERT INTO poll_heartbeats VALUES(1100000,'poll-cycle',1);
            """)
            db.executemany("INSERT INTO research_metadata VALUES(?,?)",{
                "sanitized_stock_only":"true","roster_size":"24",
                "contains_game_api_keys":"false",
                "history_days":"14","source_cutoff_epoch":"1100000",
                "row_count":"1",
            }.items())
        with sqlite3.connect(collector) as db:
            db.executescript("""
                CREATE TABLE stock_history(
                    id INTEGER PRIMARY KEY,
                    timestamp INTEGER,quantity INTEGER,source TEXT,
                    country TEXT,item_name TEXT
                );
                CREATE TABLE poll_heartbeats(timestamp INTEGER,mode TEXT,success INTEGER);
                INSERT INTO poll_heartbeats VALUES(1100000,'poll-cycle',1);
            """)
            if include_sou:
                db.executemany("""INSERT INTO stock_history(timestamp,quantity,source,country,item_name)
                           VALUES(?,?,?,?,?)""",[
                    (1000001,0,'yata','sou','Xanax'),
                    (1000500,1000,'yata','sou','Xanax'),
                    (1100001,0,'yata','sou','Xanax'),
                    (1000002,500,'yata','sou','Lion Plushie'),
                ])
        return base,collector

    def test_new_private_file_contains_original_roster_and_only_added_sou_xanax(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            root.chmod(0o700)
            base,collector=self.setup_sources(root)
            before=(base.read_bytes(),collector.read_bytes())
            target=root/OUT_NAME
            ret=build(base,collector,target)
            self.assertEqual(ret["status"],"RESEARCH_25_ITEM_SANITIZED_ARCHIVE_READY")
            self.assertEqual(ret["added_rows"],2)
            self.assertFalse(ret["production_modified"])
            self.assertEqual(base.read_bytes(),before[0])
            self.assertEqual(collector.read_bytes(),before[1])
            with sqlite3.connect(target) as db:
                md=dict(db.execute("SELECT key,value FROM research_metadata"))
                self.assertEqual(md["roster_size"],"25")
                self.assertEqual(md["row_count"],"3")
                self.assertEqual(db.execute("SELECT COUNT(*) FROM stock_history").fetchone()[0],3)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM stock_history WHERE country='sou' AND item_name='Lion Plushie'").fetchone()[0],0)
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0],"ok")
            with self.assertRaises(FileExistsError):
                build(base,collector,target)

    def test_missing_sou_fails_and_keeps_no_output(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            root.chmod(0o700)
            base,collector=self.setup_sources(root,include_sou=False)
            target=root/OUT_NAME
            with self.assertRaisesRegex(ValueError,"NO_SOUTH_AFRICA_XANAX_ROWS"):
                build(base,collector,target)
            self.assertFalse(target.exists())


if __name__=="__main__":
    unittest.main()
