"""One-shot research snapshot: never touches source data or model routing."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.v60_private_snapshot_probe import snapshot_once

T=1791540000


def seed(db,stamp=T-15):
    with sqlite3.connect(db) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE stock_history(timestamp INTEGER, item_name TEXT)")
        con.execute("CREATE TABLE poll_heartbeats(timestamp INTEGER,mode TEXT,success INTEGER)")
        con.execute("INSERT INTO stock_history VALUES(?,?)",(stamp,"Heather"))
        con.execute("INSERT INTO poll_heartbeats VALUES(?,'poll-cycle',1)",(stamp,))


class SnapshotTests(unittest.TestCase):
    def test_consistent_backup_readonly_and_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"live"/"stock.db"
            db.parent.mkdir()
            dst=Path(tmp)/"mirror"/"v60.db"
            seed(db)
            before=db.read_bytes()
            result=snapshot_once(db,dst,now_fn=lambda:T)
            self.assertEqual(result["status"],"PRIVATE_SNAPSHOT_READY")
            self.assertTrue(result["published"])
            self.assertEqual(db.read_bytes(),before)
            with sqlite3.connect(f"file:{dst}?mode=ro",uri=True) as snap:
                self.assertEqual(snap.execute("SELECT COUNT(*) FROM stock_history").fetchone()[0],1)
                self.assertEqual(snap.execute("PRAGMA quick_check").fetchone(),("ok",))
                self.assertEqual(snap.execute("PRAGMA journal_mode").fetchone(),("delete",))
            self.assertFalse(Path(str(dst)+"-wal").exists())
            self.assertFalse(Path(str(dst)+"-shm").exists())
            self.assertFalse((dst.parent/(dst.name+".v60-unpublished-tmp")).exists())

    def test_stale_source_fails_closed_without_creating_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"src"/"data.db"
            db.parent.mkdir()
            dst=Path(tmp)/"dst"/"mirror.db"
            seed(db,T-900)
            result=snapshot_once(db,dst,now_fn=lambda:T)
            self.assertEqual(result["status"],"SOURCE_HEARTBEAT_STALE")
            self.assertFalse(result["published"])
            self.assertFalse(dst.exists())

    def test_rejects_destination_inside_source_directory_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"stock.db"
            seed(db)
            with self.assertRaises(ValueError):
                snapshot_once(db,db)

    def test_existing_temp_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"src"/"stock.db"
            db.parent.mkdir()
            dst=Path(tmp)/"mirror"/"mirror.db"
            seed(db)
            dst.parent.mkdir()
            tmp_path=dst.with_name(dst.name+".v60-unpublished-tmp")
            tmp_path.write_bytes(b"must-preserve")
            with self.assertRaises(FileExistsError):
                snapshot_once(db,dst,now_fn=lambda:T)
            self.assertEqual(tmp_path.read_bytes(),b"must-preserve")

    def test_pinned_mirror_not_changed_after_source_advances(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"src"/"stock.db"
            db.parent.mkdir()
            dst=Path(tmp)/"mirror"/"mirror.db"
            seed(db)
            self.assertTrue(snapshot_once(db,dst,now_fn=lambda:T)["published"])
            with sqlite3.connect(db) as con:
                con.execute("INSERT INTO stock_history VALUES(?,?)",(T+5,"Red Fox"))
            with sqlite3.connect(dst) as con:
                self.assertEqual(con.execute("SELECT COUNT(*) FROM stock_history").fetchone()[0],1)

    def test_backup_becoming_stale_at_publish_time_is_not_released(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"src"/"stock.db"
            db.parent.mkdir()
            dst=Path(tmp)/"mirror"/"mirror.db"
            seed(db)
            ticks=iter([T,T+350])
            result=snapshot_once(db,dst,now_fn=lambda:next(ticks))
            self.assertEqual(result["status"],"SNAPSHOT_HEARTBEAT_STALE")
            self.assertFalse(dst.exists())

    def test_backup_failure_preserves_existing_published_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"src"/"stock.db"
            db.parent.mkdir()
            dst=Path(tmp)/"mirror"/"mirror.db"
            seed(db)
            self.assertTrue(snapshot_once(db,dst,now_fn=lambda:T)["published"])
            data=dst.read_bytes()
            with patch("research.v60_private_snapshot_probe.read_heartbeat",return_value=None):
                result=snapshot_once(db,dst,now_fn=lambda:T)
            self.assertFalse(result["published"])
            self.assertEqual(dst.read_bytes(),data)

if __name__=="__main__":
    unittest.main()
