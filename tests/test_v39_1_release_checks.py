"""Release-script and systemd hotfix contract; no production action."""
from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class QueueReleaseContract(unittest.TestCase):
    def test_exact_v39_parent_and_no_web_or_bot_restart(self):
        script=(ROOT/"deploy/scripts/deploy_v39_1_queue_fairness.sh").read_text()
        self.assertIn("e9ba974c96553ea36f31951b94901b7379b22624",script)
        self.assertIn('git merge --ff-only FETCH_HEAD',script)
        self.assertIn('venv/bin/python -m py_compile',script)
        self.assertIn("stock_history.db",script)
        self.assertIn("PRAGMA quick_check",script)
        self.assertIn("git branch backup/pre-v39-1-fairness-20261009 HEAD",script)
        self.assertIn("sudo systemctl restart torn-fren-poller.service",script)
        self.assertNotIn("sudo systemctl restart torn-fren-web.service",script)
        self.assertNotIn("sudo systemctl restart torn-fren-bot.service",script)
        self.assertNotIn("sudo systemctl stop torn-fren-routine-audit.service",script)
        self.assertNotIn("DROP TABLE",script)
        self.assertNotIn("DELETE FROM routine_audit_jobs_v39",script)
        self.assertNotIn("git reset --hard",script)

    def test_unit_allows_actual_db_wal_directory_but_stays_capped(self):
        unit=(ROOT/"deploy/systemd/torn-fren-routine-audit.service").read_text()
        self.assertIn("ReadWritePaths=/opt/torn-fren/data /var/lib/torn-fren",unit)
        self.assertIn("ProtectSystem=strict",unit)
        self.assertIn("CPUQuota=35%",unit)
        self.assertIn("MemoryMax=768M",unit)
        self.assertIn("Nice=17",unit)
        self.assertIn("ExecStart=/opt/torn-fren/venv/bin/python -m services.durable_audit_queue_v39",unit)

    def test_rollback_preserves_stock_and_audit_db(self):
        script=(ROOT/"deploy/scripts/rollback_v39_1_queue_fairness.sh").read_text()
        self.assertIn("backup/pre-v39-1-fairness-20261009",script)
        self.assertIn('git reset --hard "$BASE"',script)
        self.assertNotIn("rm -f /opt/torn-fren/data",script)
        self.assertNotIn("DROP TABLE",script)
        self.assertNotIn("systemctl restart torn-fren-web.service",script)


if __name__=="__main__":
    unittest.main()
