"""V57 safe error classification and journal propagation without raw exception data."""
import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

from research.v57_exception_fingerprint import fingerprint
from research import v38_v18_single_tick as v18
from research import v38_v19_single_tick as v19
from research import v38_red_fox_single_tick as redfox
from research.v38_budgeted_runner import run_tick
from research.v38_prediction_store import read

NOW=1791540000


class DiagnosticFingerprintTests(unittest.TestCase):
    def test_sqlite_types_and_safe_known_error_messages(self):
        for msg,expected in (
            ("database is locked","SQLITE_BUSY"),
            ("unable to open database file","SQLITE_CANTOPEN"),
            ("attempt to write a readonly database","SQLITE_READONLY"),
            ("no such table: secret_table","SQLITE_MISSING_TABLE"),
        ):
            with self.subTest(msg=msg):
                result=fingerprint(sqlite3.OperationalError(msg))
                self.assertEqual(result["error_type"],"OperationalError")
                self.assertEqual(result["error_tag"],expected)
                self.assertNotIn("secret_table",json.dumps(result))
                self.assertNotIn("database is locked",json.dumps(result))

    def test_red_fox_stale_asof_is_distinct_from_other_value_error(self):
        first=fingerprint(ValueError("future stock rows relative to requested as-of"))
        self.assertEqual(first["error_tag"],"SOURCE_ADVANCED_AFTER_SNAPSHOT_CHECK")
        other=fingerprint(ValueError("sensitive error with token ABCDEF"))
        self.assertEqual(other["error_tag"],"VALUE_ERROR_OTHER")
        self.assertNotIn("ABCDEF",json.dumps(other))

    def test_exception_location_is_basename_only(self):
        try:
            raise sqlite3.OperationalError("database is locked")
        except sqlite3.OperationalError as e:
            out=fingerprint(e)
        self.assertNotIn("error_module",out)
        self.assertNotIn("/home/",json.dumps(out))

    def test_v18_failure_preserves_status_with_safe_tag(self):
        with patch.object(v18,"frozen_v18_tick",
                          side_effect=sqlite3.OperationalError("database is locked")):
            with patch("sys.argv",["v18","--db","/not-used","--country","mex",
                                   "--item","Dahlia","--now",str(NOW)]):
                buf=io.StringIO()
                with contextlib.redirect_stdout(buf):
                    v18.main()
        res=json.loads(buf.getvalue())
        self.assertEqual(res["status"],"V38_NATIVE_ERROR")
        self.assertEqual(res["error_tag"],"SQLITE_BUSY")

    def test_v19_failure_preserves_status_with_safe_tag(self):
        with patch.object(v19,"inspect_live_source",
                          side_effect=sqlite3.OperationalError("unable to open database file")):
            with patch("sys.argv",["v19","--db","/not-used","--country","jap",
                                   "--item","Cherry Blossom","--now",str(NOW)]):
                buf=io.StringIO()
                with contextlib.redirect_stdout(buf):
                    v19.main()
        res=json.loads(buf.getvalue())
        self.assertEqual(res["status"],"V38_NATIVE_ERROR")
        self.assertEqual(res["error_tag"],"SQLITE_CANTOPEN")

    def test_red_fox_failure_preserves_status_with_safe_tag(self):
        with patch.object(redfox,"inspect_live_source",
                          side_effect=ValueError("future stock rows relative to requested as-of")):
            with patch("sys.argv",["redfox","--db","/not-used","--country","uni",
                                   "--item","Red Fox Plushie","--now",str(NOW)]):
                buf=io.StringIO()
                with contextlib.redirect_stdout(buf):
                    redfox.main()
        res=json.loads(buf.getvalue())
        self.assertEqual(res["status"],"V38_RED_FOX_ERROR")
        self.assertEqual(res["error_tag"],"SOURCE_ADVANCED_AFTER_SNAPSHOT_CHECK")

    def test_runner_journal_tags_are_sanitized_and_not_public(self):
        with tempfile.TemporaryDirectory() as folder:
            stock=Path(folder)/"stock.db"
            side=Path(folder)/"research.db"
            with sqlite3.connect(stock) as c:
                c.execute("""CREATE TABLE stock_history(
                    id INTEGER PRIMARY KEY,timestamp INTEGER,country TEXT,
                    item_name TEXT,quantity INTEGER)""")
                c.execute("CREATE TABLE collection_gaps(id INTEGER PRIMARY KEY)")
                c.execute("""CREATE TABLE poll_heartbeats(
                    timestamp INTEGER,mode TEXT,success INTEGER)""")
                c.execute("INSERT INTO poll_heartbeats VALUES(?,'poll-cycle',1)",
                          (NOW-20,))
                c.execute("INSERT INTO stock_history VALUES(1,?,?,?,?)",
                          (NOW-30,"uni","Heather",40))
            response={
                "status":"V38_NATIVE_ERROR",
                "error_type":"OperationalError",
                "error_tag":"SQLITE_CANTOPEN",
                "error_module":"history_service.py",
                "error_line":802,
                "raw_message":"token ABC123 /secret/privileged.db",
            }
            out=run_tick(stock_db=stock,sidecar_db=side,execute=True,
                capacity_probe=lambda:{"allowed":True},
                max_jobs=1,approved_keys=["uni:Heather"],active=["uni:Heather"],
                now=NOW,runner=lambda *a,**k:Mock(returncode=0,
                                                   stdout=json.dumps(response)),
                clock=lambda:0)
            item=out["executed"][0]
            self.assertEqual(item["error_tag"],"SQLITE_CANTOPEN")
            self.assertEqual(item["error_module"],"history_service.py")
            self.assertEqual(item["error_line"],802)
            self.assertEqual(item["status"],"V38_NATIVE_ERROR")
            self.assertNotIn("ABC123",json.dumps(out))
            self.assertNotIn("ABC123",json.dumps(read(side,NOW)))
            self.assertEqual(read(side,NOW,"uni:Heather")["worker_status"],
                             "V38_NATIVE_ERROR")

    def test_parent_rejects_untrusted_diagnostics(self):
        with tempfile.TemporaryDirectory() as folder:
            stock=Path(folder)/"stock.db"
            side=Path(folder)/"private.db"
            with sqlite3.connect(stock) as con:
                con.execute("CREATE TABLE stock_history(id INTEGER PRIMARY KEY,timestamp INTEGER,country TEXT,item_name TEXT,quantity INTEGER)")
                con.execute("CREATE TABLE collection_gaps(id INTEGER PRIMARY KEY)")
                con.execute("CREATE TABLE poll_heartbeats(timestamp INTEGER,mode TEXT,success INTEGER)")
                con.execute("INSERT INTO poll_heartbeats VALUES(?,'poll-cycle',1)",(NOW-20,))
                con.execute("INSERT INTO stock_history VALUES(1,?,?,?,?)",(NOW-20,"uni","Heather",30))
            bad={"status":"V38_NATIVE_ERROR","error_type":"OperationalError",
                 "error_tag":"SQLITE_BUSY /private/path",
                 "error_module":"/opt/torn-fren/private.py",
                 "error_line":-1}
            result=run_tick(stock_db=stock,sidecar_db=side,execute=True,
                capacity_probe=lambda:{"allowed":True},max_jobs=1,
                approved_keys=["uni:Heather"],active=["uni:Heather"],
                now=NOW,runner=lambda *a,**kw:Mock(returncode=0,
                                                    stdout=json.dumps(bad)),clock=lambda:0)
            row=result["executed"][0]
            self.assertNotIn("error_tag",row)
            self.assertNotIn("error_module",row)
            self.assertNotIn("error_line",row)


if __name__=="__main__":
    unittest.main()
