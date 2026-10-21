"""V127 opt-in private research timer safety contract."""
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
DEPLOY=ROOT/"deploy"
SVC=DEPLOY/"systemd/torn-fren-v127-earliest-shadow.service"
TMR=DEPLOY/"systemd/torn-fren-v127-earliest-shadow.timer"
INSTALL=DEPLOY/"scripts/v127_earliest_shadow_operator.sh"
LAUNCH=DEPLOY/"scripts/v127_shadow_launcher.py"


class V127PrivateRecorderSafety(unittest.TestCase):
    def test_unit_is_private_readonly_and_low_priority(self):
        unit=SVC.read_text()
        self.assertIn("User=ubuntu",unit)
        self.assertIn("Type=oneshot",unit)
        self.assertIn("ReadOnlyPaths=/opt/torn-fren/data",unit)
        self.assertIn("ReadWritePaths=/var/lib/torn-fren-v38",unit)
        self.assertIn("ProtectSystem=strict",unit)
        self.assertIn("PrivateNetwork=yes",unit)
        self.assertIn("CPUQuota=15%",unit)
        self.assertIn("MemoryMax=512M",unit)
        self.assertIn("Nice=19",unit)
        self.assertIn("NoNewPrivileges=yes",unit)
        self.assertIn("TimeoutStartSec=120",unit)
        self.assertIn("v127_shadow_launcher.py --record",unit)
        self.assertNotIn("ExecStart=/home/ubuntu/torn-fren-v38-probe/.venv/bin/python -m",unit)
        self.assertNotIn("research.v38_budgeted_runner",unit)
        self.assertNotIn("torn-fren-v38-private-shadow.service",unit)

    def test_timer_is_independent_offset_5min_nonpersistent(self):
        timer=TMR.read_text()
        self.assertIn("OnCalendar=*-*-* *:02/5:00",timer)
        self.assertIn("Persistent=false",timer)
        self.assertIn("torn-fren-v127-earliest-shadow.service",timer)
        self.assertNotIn("torn-fren-v38-private-shadow",timer)
        self.assertNotIn("OnBootSec=",timer)

    def test_no_automatic_arming_at_smoke_or_status(self):
        shell=INSTALL.read_text()
        self.assertIn("status|smoke|enable|disable",shell)
        self.assertIn('if [[ "$ACTION" == smoke ]]',shell)
        self.assertIn('if [[ "$ACTION" == status ]]',shell)
        self.assertIn('if [[ "$ACTION" == disable ]]',shell)
        self.assertIn('sudo systemctl enable --now "$TIMER"',shell)
        self.assertIn("git cat-file -e",shell)
        self.assertIn('git show "${COMMIT}:research/${module}.py"',shell)
        self.assertIn("--preview",shell)
        self.assertNotIn("systemctl stop torn-fren-v38-private-shadow",shell)
        result=subprocess.run(["bash","-n",str(INSTALL)],
                              capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        cal=subprocess.run(
            ["systemd-analyze","calendar","*-*-* *:02/5:00"],
            capture_output=True,text=True)
        if cal.returncode==0:
            self.assertIn("Normalized form",cal.stdout)

    def test_windows_carriage_return_status_is_read_only_dispatch(self):
        shell=INSTALL.read_text()
        # Test only the parser preamble: never execute the installer or
        # any enable/disable command in CI.
        start=shell.index('ACTION="${1:-status}"')
        end=shell.index('[[ "$(id -un)"',start)
        snippet=shell[start:end]
        for value in ("status", "status\r", "smoke", "enable", "disable"):
            outcome=subprocess.run(
                ["bash","-c",snippet,"v127-parse",value],
                capture_output=True,text=True)
            self.assertEqual(outcome.returncode,0,
                             (value,outcome.stderr,outcome.stdout))
        for value in ("invalid","status-mistyped","enable-extra"):
            outcome=subprocess.run(
                ["bash","-c",snippet,"v127-parse",value],
                capture_output=True,text=True)
            self.assertEqual(outcome.returncode,2,value)

    def test_launcher_does_not_load_checkout_champion_as_last_module(self):
        text=LAUNCH.read_text()
        self.assertIn("v127_stage/pinned/research",text)
        self.assertIn("assert Path(module.__file__).resolve().parent == expected",text)
        self.assertIn('mode.add_argument("--preview"',text)
        self.assertIn('mode.add_argument("--record"',text)
        self.assertNotIn("requests.get",text)
        self.assertNotIn("subprocess.run",text)
        self.assertNotIn("GenUI",text)


if __name__=="__main__":
    unittest.main()
