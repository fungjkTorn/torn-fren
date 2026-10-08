"""Static VM unit safety contract: no public V2/bot/poller service toggles."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SERVICE=(ROOT/"deploy/systemd/torn-fren-shadow-capture.service").read_text()
TIMER=(ROOT/"deploy/systemd/torn-fren-shadow-capture.timer").read_text()

class SystemdSamplingSafetyTests(unittest.TestCase):
    def test_no_service_started_by_merge_alone(self):
        self.assertIn("Type=oneshot",SERVICE)
        self.assertNotIn("[Install]",SERVICE)
        self.assertIn("User=ubuntu",SERVICE)
        self.assertIn("StateDirectory=torn-fren-shadow",SERVICE)
        self.assertIn("UMask=0077",SERVICE)
        self.assertIn("ProtectSystem=strict",SERVICE)
        self.assertIn("NoNewPrivileges=yes",SERVICE)

    def test_private_file_and_python_only(self):
        self.assertIn("EnvironmentFile=/etc/torn-fren/private-shadow.env",SERVICE)
        self.assertIn("research.v33_private_shadow_sampler",SERVICE)
        self.assertIn("--item \"can:Bear Gall\"",SERVICE)
        self.assertIn("--evidence-db /var/lib/torn-fren-shadow/capture.db",SERVICE)
        self.assertNotIn("stock_history.db",SERVICE)
        self.assertNotIn("sudo",SERVICE)

    def test_timer_does_not_replay_missed_history(self):
        self.assertIn("OnCalendar=*-*-* *:01/5:00",TIMER)
        self.assertIn("Persistent=false",TIMER)
        self.assertIn("Unit=torn-fren-shadow-capture.service",TIMER)
        self.assertNotIn("torn-fren-web.service",TIMER)
        self.assertIn("WantedBy=timers.target",TIMER)

if __name__=="__main__":unittest.main()
