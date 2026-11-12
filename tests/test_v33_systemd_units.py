"""VM timer sandbox contract, now isolated from the public server and secrets."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SERVICE=(ROOT/"deploy/systemd/torn-fren-shadow-capture.service").read_text()
TIMER=(ROOT/"deploy/systemd/torn-fren-shadow-capture.timer").read_text()

class SystemdSamplingSafetyTests(unittest.TestCase):
    def test_only_opt_in_one_shot_service(self):
        self.assertIn("Type=oneshot",SERVICE)
        self.assertNotIn("[Install]",SERVICE)
        self.assertIn("User=ubuntu",SERVICE)
        self.assertIn("StateDirectory=torn-fren-shadow",SERVICE)
        self.assertIn("UMask=0077",SERVICE)
        self.assertIn("ProtectSystem=strict",SERVICE)
        self.assertIn("NoNewPrivileges=yes",SERVICE)

    def test_no_private_token_nor_direct_public_service_replacement(self):
        self.assertNotIn("EnvironmentFile",SERVICE)
        self.assertNotIn("private-shadow.env",SERVICE)
        self.assertIn("research.v36_isolated_museum_sampler",SERVICE)
        self.assertIn("--rotate",SERVICE)
        self.assertIn("--evidence-db /var/lib/torn-fren-shadow/capture.db",SERVICE)
        self.assertIn("--db /opt/torn-fren/data/stock_history.db",SERVICE)
        self.assertNotIn("sudo",SERVICE)
        self.assertNotIn("systemctl restart",SERVICE)

    def test_timer_bounded_research_resource_usage(self):
        self.assertIn("Nice=15",SERVICE)
        self.assertIn("CPUQuota=50%",SERVICE)
        self.assertIn("MemoryMax=512M",SERVICE)
        self.assertIn("TimeoutStartSec=75",SERVICE)
        self.assertIn("OnCalendar=*-*-* *:01/5:00",TIMER)
        self.assertIn("Persistent=false",TIMER)
        self.assertIn("Unit=torn-fren-shadow-capture.service",TIMER)
        self.assertNotIn("torn-fren-web.service",TIMER)

if __name__=="__main__":unittest.main()
