"""V136 operator only stages pinned read-only reports; never arms timers."""
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"deploy/scripts/v136_run_leave_quality_morning.sh"


class MorningReadonlyOperatorTests(unittest.TestCase):
    def test_script_syntax_and_provenance(self):
        data=SCRIPT.read_text()
        result=subprocess.run(["bash","-n",str(SCRIPT)],
                              capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        for check in (
            "0a48218c0fbd48e51d6c056c421de376b47bc521",
            "git cat-file -e",
            "git show",
            "v129_full24_forward_report",
            "v131_multiledger_historical_arrival_audit",
            "v132_departure_timing_quality_audit",
            "v134_original_graph_v2_audit",
            "v135_morning_departure_brief",
            "nice -n 19 timeout 240s",
            "PYTHONDONTWRITEBYTECODE=1",
            "v128_stage/pinned/research",
            "assert Path(module.__file__).resolve().parent==stage",
        ):
            self.assertIn(check,data)
        for forbidden in (
            "systemctl enable",
            "systemctl stop",
            "systemctl restart",
            "systemctl start",
            "ExecStart",
            "sqlite3.connect(",
            "sudo ",
            "curl ",
            "requests.get(",
            "git checkout",
            "git reset",
            "--record",
        ):
            self.assertNotIn(forbidden,data)

    def test_only_old_and_new_research_sources_as_inputs(self):
        data=SCRIPT.read_text()
        self.assertIn(
            "V128=/var/lib/torn-fren-v38/v128_earliest24_shadow.db",data)
        self.assertIn(
            "V75=/var/lib/torn-fren-v38/v75_private_predictions.db",data)
        self.assertIn(
            "LIVE=/opt/torn-fren/data/stock_history.db",data)
        self.assertNotIn("torntools.com",data)
        self.assertNotIn("api.torn.com",data)


if __name__=="__main__":
    unittest.main()
