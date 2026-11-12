"""V128 operator/units: research-only 24, opt-in timer and exact source pin."""
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
SERVICE=ROOT/"deploy/systemd/torn-fren-v128-full24-shadow.service"
TIMER=ROOT/"deploy/systemd/torn-fren-v128-full24-shadow.timer"
OPERATOR=ROOT/"deploy/scripts/v128_full24_operator.sh"
LAUNCHER=ROOT/"deploy/scripts/v128_shadow_launcher.py"


class Private24OperatorContract(unittest.TestCase):
    def test_low_pressure_no_network_research_unit(self):
        unit=SERVICE.read_text()
        for line in (
            "Type=oneshot","User=ubuntu","Group=ubuntu",
            "ReadOnlyPaths=/opt/torn-fren/data",
            "ReadWritePaths=/var/lib/torn-fren-v38",
            "ProtectSystem=strict","ProtectHome=read-only",
            "PrivateNetwork=yes","NoNewPrivileges=yes",
            "CPUQuota=15%","MemoryMax=512M","Nice=19",
            "TimeoutStartSec=150","UMask=0077",
            "v128_shadow_launcher.py --record",
        ):
            self.assertIn(line,unit)
        self.assertNotIn("torn-fren-v38-private-shadow.service",unit)
        self.assertNotIn("ExecStart=/opt/torn-fren",unit)

    def test_timer_independent_and_not_persistent(self):
        timer=TIMER.read_text()
        self.assertIn("OnCalendar=*-*-* *:04/5:00",timer)
        self.assertIn("Persistent=false",timer)
        self.assertIn("torn-fren-v128-full24-shadow.service",timer)
        self.assertNotIn("torn-fren-v127-earliest-shadow.service",timer)

    def test_status_and_smoke_do_not_enable_automatic_recording(self):
        shell=OPERATOR.read_text()
        for term in (
            "status|smoke|enable|disable",
            'if [[ "$ACTION" == status ]]',
            'if [[ "$ACTION" == smoke ]]',
            "v128_shadow_launcher.py",
            "git cat-file -e",
            "git show",
            "--preview",
            'sudo systemctl enable --now "$TIMER"',
        ):
            self.assertIn(term,shell)
        self.assertNotIn('sudo systemctl stop torn-fren-v38-private-shadow.timer',shell)
        self.assertNotIn('sudo systemctl restart torn-fren-web.service',shell)
        result=subprocess.run(["bash","-n",str(OPERATOR)],capture_output=True,
                              text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        a=subprocess.run(["systemd-analyze","calendar","*-*-* *:04/5:00"],
                         capture_output=True,text=True)
        if a.returncode==0:self.assertIn("Normalized form",a.stdout)

    def test_pinned_launcher_all24_and_snapshot(self):
        code=LAUNCHER.read_text()
        self.assertIn("v128_stage/pinned/research",code)
        self.assertIn("v38_roster.json",code)
        self.assertIn("v128_full24_earliest_shadow",code)
        self.assertIn("roster_count",code)
        self.assertIn('mode.add_argument("--preview"',code)
        self.assertIn('mode.add_argument("--record"',code)
        self.assertIn("unpinned research module",code)
        self.assertNotIn("requests.get",code)
        self.assertNotIn("subprocess.run",code)

    def test_cr_safe_case_dispatch(self):
        shell=OPERATOR.read_text()
        begin=shell.index('ACTION="$(printf')
        stop=shell.index('[[ "$(id -un)"',begin)
        snippet=shell[begin:stop]
        for mode in ("status","status\r","smoke","enable","disable"):
            result=subprocess.run(
                ["bash","-c",snippet,"parse",mode],
                capture_output=True,text=True)
            self.assertEqual(result.returncode,0,(mode,result.stderr))
        for mode in ("invalid","enable-more"):
            result=subprocess.run(
                ["bash","-c",snippet,"parse",mode],
                capture_output=True,text=True)
            self.assertEqual(result.returncode,2,mode)


if __name__=="__main__":
    unittest.main()
