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
