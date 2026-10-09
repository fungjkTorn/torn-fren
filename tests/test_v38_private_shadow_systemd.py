"""No public influence, bounded CPU and exact five-item shadow allowlist."""
import shlex
import unittest
from pathlib import Path

from research.v38_readonly_resource_probe import PROBES


class PrivateShadowUnitTests(unittest.TestCase):
    def test_unit_opt_in_never_changes_polling_public_web_or_game(self):
        root=Path(__file__).parents[1]
        source=(root/"deploy/systemd/torn-fren-v38-private-shadow.service").read_text()
        timer=(root/"deploy/systemd/torn-fren-v38-private-shadow.timer").read_text()
        self.assertIn("CPUQuota=20%",source)
        self.assertIn("Nice=19",source)
        self.assertIn("MemoryMax=1024M",source)
        self.assertIn("TimeoutStartSec=105",source)
        self.assertIn("ReadOnlyPaths=/var/lib/torn-fren",source)
        self.assertIn("ReadWritePaths=/var/lib/torn-fren-v38",source)
        self.assertNotIn("profitability-v1",source)
        self.assertNotIn("web.app",source)
        self.assertNotIn("poller.py",source)
        self.assertIn("OnCalendar=*-*-* *:*:00",timer)
        command=next(line.split("=",1)[1] for line in source.splitlines()
                     if line.startswith("ExecStart="))
        argv=shlex.split(command)
        self.assertIn("--execute",argv)
        self.assertEqual(argv[argv.index("--max-jobs")+1],"5")
        self.assertEqual(argv[argv.index("--per-worker")+1],"9")
        self.assertEqual(argv[argv.index("--budget")+1],"48")
        keys=[argv[i+1] for i,v in enumerate(argv) if v=="--allow-item"]
        self.assertEqual(set(keys),set(PROBES))
        self.assertEqual(len(keys),5)
        self.assertNotIn("jap:Xanax",keys)


if __name__=="__main__":unittest.main()
