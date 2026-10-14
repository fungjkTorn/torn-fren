"""Deployment contracts for isolated GitHub-backed research runner."""
from pathlib import Path
import re
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]/"deploy"/"research_runner"


class ResearchRunnerContracts(unittest.TestCase):
    def test_shell_scripts_syntax_and_never_target_production(self):
        for name in ("install_snapshot_exporter.sh","harden_private_runner.sh","diagnose_isolation.sh"):
            file=ROOT/name
            cmd=subprocess.run(["bash","-n",str(file)],capture_output=True,text=True)
            self.assertEqual(cmd.returncode,0,cmd.stderr)
            script=file.read_text(encoding="utf8")
            self.assertIn("set -euo pipefail",script)
            self.assertNotIn("systemctl stop torn-fren-v160",script)
            self.assertNotIn("systemctl restart torn-fren-v160",script)
            self.assertNotIn("systemctl restart torn-fren-v38",script)
        diagnostic=(ROOT/"diagnose_isolation.sh").read_text()
        self.assertIn("DIAGNOSIS COMPLETE: NO WRITES",diagnostic)
        self.assertNotIn("setfacl -m",diagnostic)
        self.assertIn("NoNewPrivileges=yes",
                      (ROOT/"harden_private_runner.sh").read_text())
        self.assertIn("InaccessiblePaths=/opt/torn-fren/data",
                      (ROOT/"harden_private_runner.sh").read_text())

    def test_private_workflow_is_restricted_and_results_only(self):
        spec=(ROOT/"private_repo_workflow.template.yml").read_text()
        self.assertIn("self-hosted, Linux, torn-fren-research",spec)
        self.assertNotIn("pull_request",spec)
        self.assertIn("permissions:\n  contents: read",spec)
        self.assertIn("requests/approved_model_sha.txt",spec)
        self.assertIn("source_cutoff_epoch",spec)
        self.assertIn("sanitized_stock_only",spec)
        self.assertIn("if test -r /opt/torn-fren/data/stock_history.db",spec)
        self.assertIn("actions/upload-artifact@v4",spec)
        self.assertIn("event_report.json",spec)
        self.assertNotIn("gh auth",spec)
        self.assertNotIn("GITHUB_TOKEN",spec)

if __name__=="__main__":
    unittest.main()
