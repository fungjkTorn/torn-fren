"""Original six-core specialist launcher reproduces archived algorithms safely."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from subprocess import CompletedProcess
from unittest import TestCase
from unittest.mock import patch

from scripts import run_pc_original_specialists as original
from scripts.audit_incumbent_sources import inventory


class PcOriginalSpecialistsTests(TestCase):
    def test_documented_direct_and_module_invocations_both_start(self):
        # The direct PowerShell command failed for the owner with
        # ModuleNotFoundError: No module named 'scripts'. Exercise *both*
        # entry points in independent Python subprocesses on Windows and Linux.
        root=Path(__file__).resolve().parents[1]
        script=root/"scripts"/"run_pc_original_specialists.py"
        commands=(
            [sys.executable,"-B",str(script),"--help"],
            [sys.executable,"-B","-m","scripts.run_pc_original_specialists","--help"],
        )
        for cmd in commands:
            with self.subTest(mode=cmd[2]):
                process=subprocess.run(cmd,cwd=root,capture_output=True,
                                       text=True,timeout=30,check=False)
                self.assertEqual(process.returncode,0,
                    process.stderr[-2000:])
                self.assertIn("--source",process.stdout)
                self.assertIn("--workers",process.stdout)

    def test_all_seven_original_specialist_paths_are_in_current_checkout(self):
        self.assertEqual(len(original.JOBS),7)
        for key in original.JOBS:
            cmd=original.command(key,Path("history.db"))
            self.assertEqual(cmd[1],"-B")
            self.assertTrue(Path(cmd[2]).is_file())
            self.assertTrue("research" in Path(cmd[2]).parts)
            self.assertIn("--db",cmd)
        self.assertIn("--target",original.command("arg:Monkey Plushie",Path("history.db")))
        self.assertEqual(original.command("swi:Chamois Plushie",Path("history.db"))[-1],"chamois")
        with self.assertRaises(ValueError):
            original.command("jap:Xanax",Path("history.db"))

    def test_all_original_specialists_now_in_registry_with_resolved_path(self):
        rows=inventory()
        for key in original.JOBS:
            self.assertTrue(rows[key]["repository_file_present"],key)
            self.assertTrue(rows[key]["historical_recorded_path_outdated"],key)
            self.assertTrue(rows[key]["repository_resolved_source_path"].startswith(
                "research/plushie_champions/"))
            self.assertFalse(rows[key]["incumbent_historical_replay_verified"])
        self.assertFalse(rows["jap:Xanax"]["repository_file_present"])
        self.assertEqual(rows["jap:Xanax"]["separate_research_variant_paths"],
                         ["research/japan_xanax/renewal_shadow.py"])

    def test_original_script_backtest_uses_explicit_readonly_sqlite(self):
        for filename,_ in original.JOBS.values():
            source=(original.DIR/filename).read_text(encoding="utf-8")
            self.assertIn("ResearchContext.build(db,readonly=True)",source)

    def test_runner_records_legacy_not_restocks_and_refuses_same_source_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            old_stdout=json.dumps(dict(item="uni:Nessie Plushie",config={"lookback_h":2},
                holdout=dict(hits=2,n=3,success=2/3,coverage=1),
                validation=dict(hits=1,n=1,success=1,coverage=1)))
            mocked=CompletedProcess([],0,stdout=old_stdout,stderr="")
            with patch.object(original.subprocess,"run",return_value=mocked):
                result=original._run_item("uni:Nessie Plushie",
                    source=root/"history.db",root=root,
                    model_sha="a"*40,timeout=60)
            self.assertEqual(result["status"],"COMPLETED")
            self.assertFalse(result["summary"]["separate_physical_restock_accuracy_measured"])
            self.assertFalse(result["summary"]["directly_comparable_to_generic_30day_cohorts"])
            self.assertTrue(result["summary"]["source_sqlite_readonly"])
            self.assertTrue((root/"uni__Nessie_Plushie"/"legacy_full_result.json").is_file())
            again=original._run_item("uni:Nessie Plushie",source=root/"history.db",
                root=root,model_sha="a"*40,timeout=60)
            self.assertEqual(again["status"],"CACHED")
            self.assertEqual(again["summary"]["original_holdout"]["hits"],2)

    def test_bounds_apply_before_sqlite_open(self):
        with self.assertRaises(SystemExit):
            original.main(["--source","missing.db","--output","dummy","--workers","7"])
        with self.assertRaises(SystemExit):
            original.main(["--source","missing.db","--output","dummy",
                           "--timeout-per-item","100000"])


if __name__=="__main__":
    import unittest
    unittest.main()
