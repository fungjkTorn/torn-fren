"""Private admission hotfix changes only a capped shadow service."""
import unittest
from pathlib import Path

class ShadowCpuReleaseTests(unittest.TestCase):
    def test_only_shadow_unit_has_opt_in_cpu_environment(self):
        root=Path(__file__).parents[1]
        unit=(root/"deploy/systemd/torn-fren-v38-private-shadow.service").read_text()
        script=(root/"deploy/scripts/upgrade_v38_idle_admission.sh").read_text()
        self.assertIn("Environment=TORN_FREN_V38_IDLE_ADMISSION=1",unit)
        self.assertIn("CPUQuota=25%",unit)
        self.assertIn("Nice=19",unit)
        self.assertIn("MemoryMax=1024M",unit)
        self.assertIn("ReadOnlyPaths=/opt/torn-fren/data",unit)
        self.assertIn("ReadWritePaths=/var/lib/torn-fren-v38",unit)
        self.assertIn("dd84271a40b6e5dac2551c9fbb1291f47463c057",script)
        self.assertIn("test -z \"$(git status --porcelain)\"",script)
        self.assertIn("git merge --ff-only FETCH_HEAD",script)
        self.assertNotIn("systemctl restart",script)
        self.assertNotIn("systemctl stop",script)
        self.assertNotIn("git reset",script)
        self.assertNotIn("sudo systemctl enable",script)
        self.assertNotIn("DELETE FROM",script)

if __name__=="__main__": unittest.main()
