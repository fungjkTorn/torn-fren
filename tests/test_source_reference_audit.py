"""Audit reports candidates conservatively and performs no destructive work."""
import tempfile
import unittest
from pathlib import Path
from tools.audit_source_references import scan


class SourceReferenceAuditTests(unittest.TestCase):
    def test_known_import_and_service_references(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'run.py').write_text('from services import worker\n')
            (root / 'services').mkdir()
            (root / 'services' / '__init__.py').write_text('')
            (root / 'services' / 'worker.py').write_text('from services.helper import x\n')
            (root / 'services' / 'helper.py').write_text('x=1\n')
            (root / 'services' / 'unused.py').write_text('y=2\n')
            (root / 'deploy').mkdir()
            (root / 'deploy' / 'sample.service').write_text('ExecStart=/usr/bin/python -m services.worker\n')
            result = scan(root)
            self.assertIn('services.helper', result['reachable_static'])
            self.assertIn('services.unused', result['possible_unreferenced_review_only'])
            self.assertFalse(result['automatic_deletion_authorized'])
            self.assertIn('deploy/sample.service', result['systemd_source_references'])

    def test_real_vm_enabled_timer_is_root_and_disabled_japan_is_not(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'run.py').write_text('pass\n')
            (root / 'services').mkdir()
            (root / 'services' / 'next_six_live.py').write_text('pass\n')
            (root / 'research').mkdir()
            (root / 'research' / 'v84_japan_forward_canary.py').write_text('pass\n')
            vm = {
                'schema': 'TORNFREN_SANITIZED_SYSTEMD_DEPENDENCIES_V1',
                'units': [
                    {'unit': 'torn-fren-next-six-beta.timer',
                     'enabled': 'enabled',
                     'timer_target': 'torn-fren-next-six-beta.service'},
                    {'unit': 'torn-fren-next-six-beta.service', 'enabled': 'static',
                     'entry_modules': ['services.next_six_live'], 'entry_py_scripts': []},
                    {'unit': 'torn-fren-v85-japan-forward.timer',
                     'enabled': 'disabled',
                     'timer_target': 'torn-fren-v85-japan-forward.service'},
                    {'unit': 'torn-fren-v85-japan-forward.service', 'enabled': 'static',
                     'entry_modules': ['research.v84_japan_forward_canary'],
                     'entry_py_scripts': []},
                    {'unit': 'torn-fren-japan-private.timer',
                     'enabled': 'enabled',
                     'timer_target': 'torn-fren-japan-private.service'},
                    {'unit': 'torn-fren-japan-private.service', 'enabled': 'static',
                     'entry_modules': ['services.final_pair_live'], 'entry_py_scripts': []},
                ],
            }
            result = scan(root, vm_units=vm)
            self.assertIn('services.next_six_live', result['reachable_static'])
            self.assertIn('services.final_pair_live', result['actual_vm_modules_absent_from_checkout'])
            self.assertNotIn('research.v84_japan_forward_canary',
                             result['actual_vm_entry_modules'])
            self.assertIn('research.v84_japan_forward_canary',
                          result['possible_unreferenced_review_only'])
            self.assertEqual(len(result['actual_vm_enabled_timer_targets']), 2)
            self.assertFalse(result['automatic_deletion_authorized'])

    def test_invalid_vm_schema_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                scan(Path(td), vm_units={'schema': 'untrusted', 'units': []})

    def test_dynamic_import_marks_uncertainty(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'run.py').write_text("from importlib import import_module\nimport_module('services.maybe')\n")
            (root / 'services').mkdir()
            (root / 'services' / 'maybe.py').write_text('pass\n')
            result = scan(root)
            self.assertIn('run', result['dynamic_import_modules'])
            self.assertIn('services.maybe', result['reachable_static'])


if __name__ == '__main__':
    unittest.main()
