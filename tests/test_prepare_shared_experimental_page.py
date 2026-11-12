import unittest
from pathlib import Path
from deploy.scripts.prepare_shared_experimental_page import prepare_html


class OwnerPageTests(unittest.TestCase):
    def test_verified_owner_html_is_extended_and_drift_rejected(self):
        raw=(Path(__file__).parent/'fixtures/experimental_owner_20261012.html').read_bytes()
        html=prepare_html(raw)
        self.assertIn('SharedExperimentalRows.project',html)
        self.assertIn('sharedFetchError=true',html)
        self.assertIn('/api/experimental/v41/predictions',html)
        self.assertIn('id="graphPanel"',html)
        self.assertIn('window.refreshChampionGraph(visible)',html)
        with self.assertRaises(ValueError):prepare_html(raw+b'\n')
