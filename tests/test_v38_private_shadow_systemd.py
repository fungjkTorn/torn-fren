"""No public influence, bounded CPU and exact five-item shadow allowlist."""
import shlex
import unittest
from pathlib import Path

from research.v38_readonly_resource_probe import PROBES


class PrivateShadowUnitTests(unittest.TestCase):
    def test_research_operator_script_refuses_busy_or_unfixed_production(self):
        root=Path(__file__).parents[1]
        source=(root/"deploy/scripts/arm_v38_five_model_canary.sh").read_text()
        self.assertIn("dd84271a40b6e5dac2551c9fbb1291f47463c057",source)
        self.assertIn("research.v38_shadow_canary_preflight",source)
        self.assertIn("research.v38_readonly_resource_probe",source)
        self.assertIn("timeout 190s",source)
        self.assertIn("--timeout 25 --budget 150",source)
        self.assertIn("FIVE-MODEL READ-ONLY BENCHMARK ACCEPTED",source)
        self.assertIn("for attempt in $(seq 1 13)",source)
        self.assertIn("sleep 20",source)
        self.assertIn("READY=0",source)
        self.assertIn('if [ "$READY" -ne 1 ]; then',source)
        self.assertNotIn("max_load_per_slot=1.0",source)
        self.assertNotIn("systemctl restart",source)
        self.assertIn("research.v38_v39_host_gate",source)
        self.assertIn('DB="/opt/torn-fren/data/stock_history.db"',source)
        self.assertIn("curl -fsS",source)
        self.assertIn("dd84271a40b6e5dac2551c9fbb1291f47463c057",source)
        self.assertIn("torn-fren-v38-private-shadow.timer",source)
        self.assertNotIn("systemctl restart",source)
        self.assertNotIn("git reset",source)
        self.assertNotIn("  --all ",source)

    def test_unit_opt_in_never_changes_polling_public_web_or_game(self):
        root=Path(__file__).parents[1]
        source=(root/"deploy/systemd/torn-fren-v38-private-shadow.service").read_text()
        timer=(root/"deploy/systemd/torn-fren-v38-private-shadow.timer").read_text()
        self.assertIn("CPUQuota=25%",source)
        self.assertIn("Nice=19",source)
        self.assertIn("MemoryMax=1024M",source)
        self.assertIn("TimeoutStartSec=240",source)
        self.assertIn("ReadOnlyPaths=/opt/torn-fren/data",source)
        self.assertIn("ConditionPathExists=/opt/torn-fren/data/stock_history.db",source)
        self.assertIn("--db /opt/torn-fren/data/stock_history.db",source)
        self.assertIn("ReadWritePaths=/var/lib/torn-fren-v38",source)
        self.assertNotIn("profitability-v1",source)
        self.assertNotIn("web.app",source)
        self.assertNotIn("poller.py",source)
        self.assertIn("OnCalendar=*-*-* *:0/5:00",timer)
        command=next(line.split("=",1)[1] for line in source.splitlines()
                     if line.startswith("ExecStart="))
        argv=shlex.split(command)
        self.assertIn("--execute",argv)
        self.assertEqual(argv[argv.index("--max-jobs")+1],"5")
        self.assertEqual(argv[argv.index("--per-worker")+1],"30")
        self.assertEqual(argv[argv.index("--budget")+1],"180")
        keys=[argv[i+1] for i,v in enumerate(argv) if v=="--allow-item"]
        self.assertEqual(set(keys),set(PROBES))
        self.assertEqual(len(keys),5)
        self.assertNotIn("jap:Xanax",keys)


if __name__=="__main__":unittest.main()
