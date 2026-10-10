"""V59: bounded retry only for frozen read-only history and safe SQLite codes."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from services import history_service
from services import frozen_candidate_worker_v31 as frozen
from research.v38_readonly_retry import read_with_retry
from research.v57_exception_fingerprint import fingerprint
from research.v38_budgeted_runner import run_tick

NOW=1791540000


class V59ReadOnlyRetryTests(unittest.TestCase):
    def _install(self, db):
        patches = (
            patch.object(history_service,"DB_PATH"),
            patch.object(history_service,"_connect"),
            patch.object(history_service,"init_db"),
            patch.object(history_service,"_DB_READY"),
        )
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        frozen._install_frozen_readonly_history(history_service,db)

    def _source(self,folder):
        db=Path(folder)/"stock.db"
        with sqlite3.connect(db) as con:
            con.executescript("""
                CREATE TABLE stock_history (
                    id INTEGER PRIMARY KEY,
                    timestamp INTEGER,
                    country TEXT,
                    item_name TEXT,
                    quantity INTEGER,
                    source TEXT
                );
                CREATE TABLE collection_gaps (
                    id INTEGER PRIMARY KEY,
                    start_timestamp INTEGER,
                    end_timestamp INTEGER,
                    reason TEXT
                );
                CREATE TABLE poll_heartbeats (
                    timestamp INTEGER, mode TEXT, success INTEGER
                );
                INSERT INTO stock_history VALUES (1,1791540000,'uni','Heather',40,'synthetic');
                INSERT INTO poll_heartbeats VALUES(1791539990,'poll-cycle',1);
            """)
        return db

    def test_synthetic_readonly_history_has_bounded_execute_retry_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=self._source(tmp)
            self._install(db)
            with history_service._connect() as conn:
                self.assertEqual(conn.execute("SELECT count(*) FROM stock_history").fetchone()[0],1)
                self.assertEqual(conn.execute("PRAGMA query_only").fetchone()[0],1)
                with self.assertRaises(sqlite3.OperationalError):
                    conn.execute("UPDATE stock_history SET quantity=100")
            with self.assertRaises(sqlite3.ProgrammingError):
                conn.execute("SELECT 1")
            self.assertIn("read_with_retry",type(conn).execute.__code__.co_names)
            with sqlite3.connect(db) as con:
                self.assertEqual(con.execute("SELECT quantity FROM stock_history").fetchone()[0],40)

    def test_transient_open_cantopen_uses_bounded_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=self._source(tmp)
            self._install(db)
            original=sqlite3.connect
            calls=[]
            def flaky(*args,**kw):
                calls.append(1)
                if len(calls)<3:
                    raise sqlite3.OperationalError("unable to open database file")
                return original(*args,**kw)
            real_retry=frozen.read_with_retry
            with patch.object(frozen.sqlite3,"connect",side_effect=flaky):
                with patch.object(frozen,"read_with_retry",
                    side_effect=lambda fn,**kw:real_retry(fn,sleep=lambda _:None,**kw)):
                    with history_service._connect() as conn:
                        self.assertEqual(conn.execute("SELECT 1").fetchone()[0],1)
            self.assertEqual(len(calls),3)

    def test_sqlite_retry_only_retryable_and_never_busy_loops_forever(self):
        calls=[]
        def failing():
            calls.append(1)
            raise sqlite3.OperationalError("unable to open database file")
        with self.assertRaises(sqlite3.OperationalError):
            read_with_retry(failing,sleep=lambda _:None,delays=(.15,.35,.65))
        self.assertEqual(len(calls),4)
        reads=[]
        def success_after_two():
            reads.append(1)
            if len(reads)<3:
                raise sqlite3.OperationalError("database is locked")
            return {"ok": True}
        self.assertEqual(read_with_retry(success_after_two,sleep=lambda _:None,
                                         delays=(.15,.35,.65)),{"ok":True})
        self.assertEqual(len(reads),3)
        attempts=[]
        def readonly_failure():
            attempts.append(1)
            raise sqlite3.OperationalError("attempt to write a readonly database")
        with self.assertRaises(sqlite3.OperationalError):
            read_with_retry(readonly_failure,sleep=lambda _:None,
                            delays=(.15,.35,.65))
        self.assertEqual(len(attempts),1)

    def test_real_sqlite_error_code_is_numeric_without_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=(Path(tmp)/"missing.db").as_uri()+"?mode=ro"
            with self.assertRaises(sqlite3.OperationalError) as cm:
                sqlite3.connect(path,uri=True)
            result=fingerprint(cm.exception)
            self.assertEqual(result["error_tag"],"SQLITE_CANTOPEN")
            self.assertEqual(result["sqlite_extended_code"] & 255,sqlite3.SQLITE_CANTOPEN)
            self.assertNotIn(tmp,json.dumps(result))

    def test_runner_private_journal_adds_numeric_code_not_public_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=self._source(tmp)
            side=Path(tmp)/"side.db"
            worker={
                "status":"V38_NATIVE_ERROR",
                "error_type":"OperationalError",
                "error_tag":"SQLITE_CANTOPEN",
                "sqlite_extended_code":sqlite3.SQLITE_CANTOPEN,
                "raw_message":"DO-NOT-PROPAGATE",
            }
            out=run_tick(stock_db=db,sidecar_db=side,execute=True,
                capacity_probe=lambda:{"allowed":True},
                max_jobs=1,approved_keys=["uni:Heather"],active=["uni:Heather"],
                now=NOW,runner=lambda *a,**kw:Mock(returncode=0,
                                                   stdout=json.dumps(worker)),
                clock=lambda:0)
            item=out["executed"][0]
            self.assertEqual(item["sqlite_extended_code"],sqlite3.SQLITE_CANTOPEN)
            self.assertNotIn("DO-NOT-PROPAGATE",json.dumps(item))
            with sqlite3.connect(side) as c:
                cols=[row[1] for row in c.execute("PRAGMA table_info(inference_attempts)")]
                self.assertNotIn("sqlite_extended_code",cols)
                self.assertEqual(c.execute("SELECT status FROM inference_attempts").fetchone()[0],
                                 "V38_NATIVE_ERROR")


if __name__=="__main__":
    unittest.main()
