"""V64 reports failed private mirror stage without paths, SQL, or false success."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from research.v63_full_mirror_smoke import smoke, stage_error, exact_roster
from research.v60_private_snapshot_probe import snapshot_once

NOW=1791540000


def setup_source(path):
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("""CREATE TABLE stock_history(
            id INTEGER PRIMARY KEY, timestamp INTEGER,
            country TEXT,item_name TEXT,quantity INTEGER,source TEXT)""")
        db.execute("""CREATE TABLE poll_heartbeats(
            timestamp INTEGER,mode TEXT,success INTEGER)""")
        db.execute("""CREATE TABLE collection_gaps(
            id INTEGER PRIMARY KEY, start_timestamp INTEGER,
            end_timestamp INTEGER,reason TEXT)""")
        db.execute("INSERT INTO stock_history VALUES(1,?,?,?,?,?)",
                   (NOW-20,"uni","Heather",44,"synthetic"))
        db.execute("INSERT INTO poll_heartbeats VALUES(?,'poll-cycle',1)",
                   (NOW-10,))


class V64MirrorDiagnosticTests(unittest.TestCase):
    def setUp(self):
        td=tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        root=Path(td.name)
        self.source=root/"source"/"stock.db"
        self.source.parent.mkdir()
        setup_source(self.source)
        self.snapshot=root/"private"/"mirror.db"
        self.sidecar=root/"private"/"probe.db"

    def backup(self,source,destination):
        return snapshot_once(source,destination,now_fn=lambda:NOW)

    def test_sqlite_snapshot_failure_reports_code_and_does_not_infer(self):
        exc=sqlite3.OperationalError("private/source/secrets must not leak")
        exc.sqlite_errorcode=264
        runner=Mock()
        def fail(*args):
            raise exc
        output=smoke(source=self.source,snapshot=self.snapshot,
                     sidecar=self.sidecar,snapshotter=fail,infer=runner)
        self.assertEqual(output["status"],"V63_SNAPSHOT_ERROR")
        self.assertEqual(output["stage"],"SNAPSHOT")
        self.assertEqual(output["error_tag"],"SQLITE_READONLY")
        self.assertEqual(output["sqlite_extended_code"],264)
        self.assertEqual(output["executed_count"],0)
        self.assertFalse(output["collector_written"])
        self.assertNotIn("secrets",repr(output))
        runner.assert_not_called()
        self.assertFalse(self.sidecar.exists())

    def test_runner_failure_reports_stage_and_safe_sqlite_code(self):
        exc=sqlite3.OperationalError("must not print db path")
        exc.sqlite_errorcode=14
        def fail(**kwargs):
            raise exc
        output=smoke(source=self.source,snapshot=self.snapshot,
                     sidecar=self.sidecar,snapshotter=self.backup,
                     infer=fail,clock=lambda:NOW)
        self.assertEqual(output["status"],"V63_RUNNER_ERROR")
        self.assertEqual(output["error_tag"],"SQLITE_CANTOPEN")
        self.assertEqual(output["sqlite_extended_code"],14)
        self.assertFalse(output["collector_written"])
        self.assertNotIn("db path",str(output))
        self.assertFalse(self.sidecar.exists())

    def test_final_snapshot_age_failure_reports_stage_and_attempted_count(self):
        keys=exact_roster()
        infer=Mock(return_value={"mode":"EXECUTED_RESEARCH_ONLY",
                  "executed":[{"item_key":keys[0],"status":"RESEARCH_PROPOSAL_ONLY"}]})
        exc=sqlite3.OperationalError("missing file /secret")
        exc.sqlite_errorcode=14
        with patch("research.v63_full_mirror_smoke.source_age",side_effect=exc):
            output=smoke(source=self.source,snapshot=self.snapshot,
                         sidecar=self.sidecar,snapshotter=self.backup,
                         infer=infer,clock=lambda:NOW)
        self.assertEqual(output["status"],"V63_FINAL_FRESHNESS_ERROR")
        self.assertEqual(output["executed_count"],1)
        self.assertEqual(output["sqlite_extended_code"],14)
        self.assertNotIn("/secret",repr(output))

    def test_non_sqlite_exception_is_sanitized(self):
        exc=OSError("sensitive /var/private/path")
        result=stage_error("SNAPSHOT",exc)
        self.assertEqual(result["stage"],"SNAPSHOT")
        self.assertEqual(result["error_type"],"OSError")
        self.assertNotIn("/var/private/path",str(result))

    def test_regular_valid_result_is_not_diagnostic_failure(self):
        keys=exact_roster()
        infer=Mock(return_value={"mode":"EXECUTED_RESEARCH_ONLY",
            "executed":[{"item_key":k,"status":"RESEARCH_PROPOSAL_ONLY"}
                        for k in keys]})
        output=smoke(source=self.source,snapshot=self.snapshot,
                     sidecar=self.sidecar,snapshotter=self.backup,
                     infer=infer,clock=lambda:NOW)
        self.assertEqual(output["status"],"V63_FULL_MIRROR_EXECUTED")
        self.assertEqual(output["proposal_count"],19)
        self.assertEqual(output["native_error_count"],0)
        self.assertEqual(output["end_heartbeat_age_seconds"],10)


if __name__ == "__main__":
    unittest.main()
