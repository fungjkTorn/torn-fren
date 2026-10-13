"""V160 isolated operator safety tests."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SH=ROOT/"deploy/scripts/v160_forward24_operator.sh"
LAUNCH=ROOT/"deploy/scripts/v160_forward_shadow_launcher.py"
SERVICE=ROOT/"deploy/systemd/torn-fren-v160-forward24.service"
TIMER=ROOT/"deploy/systemd/torn-fren-v160-forward24.timer"


class PrivateV160OperatorTests(unittest.TestCase):
    def test_explicit_enable_only_and_status_default(self):
        script=SH.read_text(encoding="utf-8")
        self.assertIn("${1:-status}",script)
        self.assertIn('if [[ "$ACTION" == status ]]',script)
        self.assertIn("smoke|record|report|enable|disable",script)
        self.assertIn('if [[ "$ACTION" == smoke ]]',script)
        self.assertIn("sudo systemctl enable --now",script)
        self.assertIn("sudo systemctl disable --now",script)
        self.assertIn('git show "${PIN}:research/${name}.py"',script)
        self.assertIn("v160_prospective_v151_shadow",script)
        self.assertIn("v161_prospective_v151_forward_report",script)
        self.assertIn("v38_roster.json",script)
        self.assertIn('test -r "$COLLECTOR"',script)

    def test_new_timer_and_service_isolate_budget(self):
        service=SERVICE.read_text(encoding="utf-8")
        timer=TIMER.read_text(encoding="utf-8")
        for needed in (
            "Type=oneshot","User=ubuntu","PrivateNetwork=yes",
            "ProtectSystem=strict","ReadOnlyPaths=/opt/torn-fren/data",
            "ReadWritePaths=/var/lib/torn-fren-v38","CPUQuota=30%",
            "MemoryMax=512M","flock -n",
            "v160_forward_shadow_launcher.py --record"):
            self.assertIn(needed,service)
        self.assertIn("Persistent=false",timer)
        self.assertIn("torn-fren-v160-forward24.service",timer)
        self.assertNotIn("web/app.py",service)

    def test_launcher_supports_only_three_modes_and_pinned_imports(self):
        script=LAUNCH.read_text(encoding="utf-8")
        for name in ('"--preview"','"--record"','"--report"',
                     "unpinned shadow module",
                     "capture.capture_once(record=a.record)",
                     "report.score(days=2)"):
            self.assertIn(name,script)
        self.assertNotIn("web.app",script)


if __name__=="__main__":
    unittest.main()
