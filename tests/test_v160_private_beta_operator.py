"""Guard a genuinely usable private V160 beta without production drift."""
import importlib.util
import subprocess
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OPERATOR=ROOT/"deploy/scripts/v160_private_beta_operator.sh"
UNIT=ROOT/"deploy/systemd/torn-fren-v160-beta-board.service"
BOARD=ROOT/"deploy/scripts/v160_private_beta_board.py"

class PrivateBetaOperatorTests(unittest.TestCase):
    def test_shell_syntax_and_explicit_actions(self):
        script=OPERATOR.read_text(encoding="utf-8")
        subprocess.run(["bash","-n",str(OPERATOR)],check=True)
        self.assertIn("install|status|stop",script)
        self.assertIn("ACTION=status",script)
        self.assertIn('git show "$PIN:deploy/scripts/v160_private_beta_board.py"',script)
        self.assertIn('git show "$PIN:deploy/systemd/$UNIT"',script)
        self.assertIn('sudo systemctl enable --now "$UNIT"',script)
        self.assertIn('sudo systemctl disable --now "$UNIT"',script)
        self.assertIn('r=m["snapshot"]()',script)
        self.assertIn('if not r["healthy"] or r["recorded_items"]!=24:',script)
        self.assertIn("STOP beta service already active on different source",script)
        self.assertNotIn("web/app.py",script)
        self.assertNotIn("systemctl restart torn-fren-web",script)
        self.assertNotIn("torn-fren-v160-forward24.timer",script)

    def test_loopback_only_read_only_service(self):
        unit=UNIT.read_text(encoding="utf-8")
        board=BOARD.read_text(encoding="utf-8")
        self.assertIn("User=ubuntu",unit)
        self.assertIn("NoNewPrivileges=yes",unit)
        self.assertIn("ProtectSystem=strict",unit)
        self.assertIn("ProtectHome=read-only",unit)
        self.assertIn("ReadOnlyPaths=/var/lib/torn-fren-v38",unit)
        self.assertIn("CPUQuota=5%",unit)
        self.assertIn("MemoryMax=128M",unit)
        self.assertIn("RestrictAddressFamilies=AF_INET AF_UNIX",unit)
        self.assertIn('("127.0.0.1",a.port)',board)
        self.assertNotIn('("0.0.0.0"',board)
        self.assertIn('"?mode=ro"',board)
        self.assertIn('PRAGMA query_only=ON',board)
        self.assertNotIn("web/app.py",unit)
        self.assertNotIn("0.0.0.0:8765",unit)

    def test_rollback_safe_upgrade_only_touches_private_beta(self):
        upgrade=ROOT/"deploy/scripts/v160_beta_safe_upgrade.sh"
        script=upgrade.read_text(encoding="utf-8")
        subprocess.run(["bash","-n",str(upgrade)],check=True)
        self.assertIn("torn-fren-v160-beta-board.service",script)
        self.assertIn('systemctl is-active --quiet "$UNIT"',script)
        self.assertIn('git show "$PIN:deploy/scripts/v160_private_beta_board.py"',script)
        self.assertIn('python3 -m py_compile "$NEW"',script)
        self.assertIn('r=m["snapshot"]()',script)
        self.assertIn('cp -p "$CODE" "$BACKUP"',script)
        self.assertIn('install -m 0700 "$BACKUP" "$CODE"',script)
        self.assertIn("Where should I fly?",script)
        self.assertIn("NEW_PRIVATE_BETA_HTTP_PASS 24/24",script)
        self.assertNotIn("systemctl restart torn-fren-web",script)
        self.assertNotIn("torn-fren-v160-forward24.timer",script)
        self.assertNotIn("stock_history.db",script)
        self.assertNotIn('sudo systemctl enable --now',script)

    def test_user_recheck_upgrade_is_only_for_private_beta(self):
        upgrade=ROOT/"deploy/scripts/v160_beta_decision_and_recheck_upgrade.sh"
        script=upgrade.read_text(encoding="utf-8")
        subprocess.run(["bash","-n",str(upgrade)],check=True)
        self.assertIn("torn-fren-v160-beta-board.service",script)
        self.assertIn("v160_single_item_recheck.py",script)
        self.assertIn('git show "$PIN:deploy/scripts/v160_private_beta_board.py"',script)
        self.assertIn('git show "$PIN:deploy/scripts/v160_single_item_recheck.py"',script)
        self.assertIn("SINGLE-ITEM",script)
        self.assertIn("READ-ONLY",script)
        self.assertIn('install -m 0700 "$OLD" "$CODE"',script)
        self.assertIn('sudo systemctl restart "$UNIT"',script)
        self.assertNotIn("sudo systemctl restart torn-fren-web",script)
        self.assertNotIn("torn-fren-v160-forward24.timer",script)
        self.assertNotIn("systemctl enable --now",script)

    def test_unit_python_file_exists_and_is_stdlib_only(self):
        self.assertTrue(BOARD.is_file())
        spec=importlib.util.spec_from_file_location("private_beta_check",BOARD)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.MAX_ROWS,24)
        self.assertEqual(module.POLICY,"v160_v151_independent_paired_asissued_20261013")

if __name__=="__main__":
    unittest.main()
