"""V37 surgical production regression: sqlite contexts must close OS handles."""
from __future__ import annotations
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import history_service as hs


class SQLiteHandleSafety(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/"nested"/"stock_history.db"
        self.path_patch=patch.object(hs,"DB_PATH",self.db)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)

    def test_commits_and_closes(self):
        with hs._connect() as conn:
            conn.execute("CREATE TABLE checks(value INTEGER)")
            conn.execute("INSERT INTO checks(value) VALUES (17)")
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")
        with sqlite3.connect(self.db) as reader:
            self.assertEqual(reader.execute("SELECT value FROM checks").fetchone()[0],17)

    def test_rollback_and_close_on_error(self):
        with hs._connect() as conn:
            conn.execute("CREATE TABLE checks(value INTEGER)")
        try:
            with hs._connect() as conn:
                conn.execute("INSERT INTO checks VALUES (12)")
                raise RuntimeError("intentional rollback")
        except RuntimeError:
            pass
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")
        with sqlite3.connect(self.db) as reader:
            self.assertEqual(reader.execute("SELECT COUNT(*) FROM checks").fetchone()[0],0)

    @unittest.skipUnless(os.path.isdir("/proc/self/fd"),"Linux fd probe")
    def test_2000_queries_keep_fd_count_stable(self):
        with hs._connect() as conn:
            conn.execute("CREATE TABLE checks(value INTEGER)")
            conn.execute("PRAGMA journal_mode=WAL")
        start=len(os.listdir("/proc/self/fd"))
        for i in range(2000):
            with hs._connect() as conn:
                conn.execute("SELECT COUNT(*) FROM checks").fetchone()
                if i%300==0:
                    conn.execute("INSERT INTO checks VALUES (?)",(i,))
        finish=len(os.listdir("/proc/self/fd"))
        self.assertLessEqual(finish,start+8,(start,finish))
        with sqlite3.connect(self.db) as reader:
            self.assertEqual(reader.execute("SELECT COUNT(*) FROM checks").fetchone()[0],7)

    def test_initialization_and_recovery_reuse_closed_connections(self):
        with patch.object(hs,"_DB_READY",False):
            hs.init_db()
        with hs._connect() as conn:
            self.assertIn("stock_history",{
                r[0] for r in conn.execute("SELECT name FROM sqlite_master")
            })
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


if __name__=="__main__":
    unittest.main()
