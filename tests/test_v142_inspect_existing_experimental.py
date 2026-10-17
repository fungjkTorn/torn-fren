"""V142 read-only inspection script stays informational and reversible."""
import subprocess
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"deploy/scripts/v142_inspect_existing_experimental.sh"

class ExistingBetaProbeSafetyTests(unittest.TestCase):
    def test_bash_syntax(self):
        r=subprocess.run(["bash","-n",str(SCRIPT)],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
    def test_localhost_only_and_no_mutating_service_or_db(self):
        s=SCRIPT.read_text()
        self.assertIn("http://127.0.0.1:8000",s)
        self.assertIn("/experimental",s)
        self.assertIn("/api/experimental/v41/predictions",s)
        self.assertIn('"/"',s)
        self.assertIn("sha256",s)
        for dangerous in (
            "systemctl restart","systemctl stop","systemctl start",
            "systemctl enable","systemctl disable","pip install",
            "sqlite3.connect","sudo cp","sudo rm","git checkout",
            "git reset","os.environ","print(content)","print(payload)",
        ):
            self.assertNotIn(dangerous,s)
    def test_probe_explicitly_accounts_for_24_existing_items(self):
        s=SCRIPT.read_text()
        self.assertIn('assert len(BASE24) == 24',s)
        self.assertIn('missing_24',s)
        self.assertIn('duplicate_item_keys',s)
        self.assertIn('v87_dropin_exists',s)
        self.assertIn('html_sha256',s)
if __name__=="__main__":
    unittest.main()
