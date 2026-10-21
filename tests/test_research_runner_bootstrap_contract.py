"""Deployment contracts for isolated GitHub-backed research runner."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import json
import unittest

ROOT=Path(__file__).resolve().parents[1]/"deploy"/"research_runner"


class ResearchRunnerContracts(unittest.TestCase):
    def test_shell_scripts_syntax_and_never_target_production(self):
        for name in ("install_snapshot_exporter.sh","harden_private_runner.sh","diagnose_isolation.sh","complete_isolation_acl.sh","prepare_private_runner_user.sh","install_and_harden_registered_runner.sh","tune_snapshot_for_forward.sh",
                     "install_forward_snapshot_lane.sh","audit_vm_retention_readonly.sh"):
            file=ROOT/name
            cmd=subprocess.run(["bash","-n",str(file)],capture_output=True,text=True)
            self.assertEqual(cmd.returncode,0,cmd.stderr)
            script=file.read_text(encoding="utf8")
            self.assertIn("set -euo pipefail",script)
            self.assertNotIn("systemctl stop torn-fren-v160",script)
            self.assertNotIn("systemctl restart torn-fren-v160",script)
            self.assertNotIn("systemctl restart torn-fren-v38",script)
        fast=(ROOT/"tune_snapshot_for_forward.sh").read_text()
        self.assertIn('sudo systemctl restart "$TIMER"',fast)
        self.assertNotIn('sudo systemctl restart "$UNIT"',fast)
        self.assertNotIn('systemctl restart torn-fren-v160',fast)
        self.assertNotIn('sudo systemctl restart torn-fren-',fast)
        self.assertIn('OnUnitInactiveSec=2min',fast)
        self.assertIn('AccuracySec=10s',fast)
        self.assertIn('--days 14',fast)
        self.assertIn('heartbeat_provider_field_present',fast)
        self.assertIn('sudo install -o root -g root -m 0644 "$BACKUP" "$EXPORTER"',fast)
        self.assertIn('DRY_RUN_OK',fast)
        lane=(ROOT/"install_forward_snapshot_lane.sh").read_text()
        self.assertIn("stock_history_forward.db",lane)
        self.assertIn("stock_history_research.db",lane)
        self.assertIn("OnUnitInactiveSec=90s",lane)
        self.assertIn("CPUQuota=40%",lane)
        self.assertIn("MemoryMax=640M",lane)
        self.assertIn("TimeoutStartSec=120",lane)
        self.assertIn("--days 14",lane)
        self.assertIn("heartbeat_provider_field_present",lane)
        self.assertIn('test ! -L "$SRC"',lane)
        self.assertIn('sudo systemctl start "$SERVICE"',lane)
        self.assertIn('sudo systemctl enable --now "$TIMER"',lane)
        self.assertIn("DRY_RUN_OK",lane)
        self.assertNotIn('sudo systemctl restart "$OLD_TIMER"',lane)
        self.assertNotIn("systemctl restart torn-fren-v160",lane)
        self.assertNotIn("rm -rf",lane)
        storage=(ROOT/"audit_vm_retention_readonly.sh").read_text()
        self.assertIn("INVENTORY_COMPLETE_NO_DELETES",storage)
        self.assertIn("sites-enabled",storage)
        self.assertIn("systemctl list-timers",storage)
        self.assertNotIn("rm -rf",storage)
        self.assertNotIn("systemctl stop",storage)
        self.assertNotIn("systemctl restart",storage)
        acl=(ROOT/"complete_isolation_acl.sh").read_text()
        self.assertIn('setfacl -m u:tornresearch:---',acl)
        self.assertIn('setfacl -x u:tornresearch',acl)
        self.assertIn('readlink -e -- "$DATA_LINK"',acl)
        self.assertIn('sudo -n -u ubuntu test -r "$SRC"',acl)
        self.assertIn('sudo -n -u "$USER" test -r "$RESEARCH"',acl)
        self.assertIn('sudo systemctl enable --now "$TIMER"',acl)
        self.assertNotIn("chmod 660",acl)
        self.assertNotIn("chmod 640",acl)
        self.assertNotIn("chown -R",acl)
        self.assertNotIn("setfacl -R",acl)
        environment=(ROOT/"prepare_private_runner_user.sh").read_text()
        self.assertIn("tornresearch",environment)
        self.assertIn("sudo -n -u tornresearch test -r \"$SNAP\"",environment)
        self.assertIn("if sudo -n -u tornresearch test -r \"$SRC\"",environment)
        self.assertIn("numpy==1.26.4",environment)
        self.assertIn("snapshot refresh timer inactive",environment)
        self.assertNotIn("systemctl restart torn-fren",environment)
        installer=(ROOT/"install_and_harden_registered_runner.sh").read_text()
        self.assertIn('sudo -n test -f "$RUNNER/.runner"',installer)
        self.assertIn('sudo -n test -f "$RUNNER/.service"',installer)
        self.assertIn('./svc.sh install tornresearch',installer)
        self.assertIn('sudo -n bash "$TEMP" "$UNIT"',installer)
        self.assertIn("Runner intentionally NOT STARTED",installer)
        self.assertIn('systemctl is-active --quiet "$UNIT"',installer)
        self.assertIn('torn-fren-research-snapshot.timer',installer)
        self.assertNotIn('./svc.sh start',installer)
        self.assertNotIn('./run.sh',installer)
        self.assertNotIn("chmod 755",installer)
        diagnostic=(ROOT/"diagnose_isolation.sh").read_text()
        self.assertIn("DIAGNOSIS COMPLETE: NO WRITES",diagnostic)
        self.assertNotIn("setfacl -m",diagnostic)
        self.assertIn("NoNewPrivileges=yes",
                      (ROOT/"harden_private_runner.sh").read_text())
        self.assertIn("InaccessiblePaths=/opt/torn-fren/data",
                      (ROOT/"harden_private_runner.sh").read_text())

    def test_real_runner_registration_parsers_accept_utf8_bom(self):
        """GitHub config.sh writes .runner as UTF-8 BOM JSON on ARM64.

        Execute both EXACT embedded Python preflight snippets on a fixture,
        not just a source substring assertion, so the previous VM error
        cannot recur before systemd service installation.
        """
        validators=[
            ("install_and_harden_registered_runner.sh", "VERIFY_SCOPE", True),
            ("harden_private_runner.sh", "CHECK_SCOPE", False),
        ]
        expected="https://github.com/fungjktorn/torn-fren-research-private"
        for filename,label,extra_arg in validators:
            src=(ROOT/filename).read_text(encoding="utf8")
            pattern=r"<<'"+label+r"'\n(.*?)\n"+label
            match=re.search(pattern,src,re.DOTALL)
            self.assertIsNotNone(match, filename+" missing parser body")
            snippet=match.group(1)
            with tempfile.TemporaryDirectory() as tmp:
                config=Path(tmp)/".runner"
                for bom in (False,True):
                    config.write_bytes(
                        ("\ufeff" if bom else "").encode("utf8")+
                        json.dumps({"gitHubUrl":
                            "https://github.com/fungjkTorn/torn-fren-research-private"}).encode("utf8"))
                    args=[sys.executable,"-",str(config)]
                    if extra_arg:
                        args.append(expected)
                    proc=subprocess.run(args,input=snippet,text=True,
                                        capture_output=True,timeout=8)
                    self.assertEqual(proc.returncode,0,
                        f"{filename} bom={bom}: {proc.stderr} {proc.stdout}")
                config.write_bytes(("\ufeff"+json.dumps(
                    {"gitHubUrl":"https://github.com/fungjkTorn/torn-fren"}
                )).encode("utf8"))
                args=[sys.executable,"-",str(config)]
                if extra_arg:
                    args.append(expected)
                bad=subprocess.run(args,input=snippet,text=True,
                                   capture_output=True,timeout=8)
                self.assertNotEqual(bad.returncode,0,
                    "public GitHub repo must always be rejected")

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
