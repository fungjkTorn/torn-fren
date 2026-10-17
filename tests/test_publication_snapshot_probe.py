import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_continuous_departure_replay as fixtures
from test_travel_read_model import departure_snapshot,T
from research.publication_snapshot_probe import measure


class PublicationTests(unittest.TestCase):
    def test_build_cost_can_exhaust_tolerance_without_renewing_issue(self):
        with tempfile.TemporaryDirectory() as td:
            db=fixtures.ContinuousTests().fixture(Path(td));before=db.read_bytes()
            snapshot=departure_snapshot(T)
            snapshot['item_departure_recommendations']['mex:Jaguar Plushie']['execution_policy']='publication_delay_30s_v1'
            with patch('research.publication_snapshot_probe.prepare',return_value=snapshot),patch(
                    'research.publication_snapshot_probe.time.perf_counter',side_effect=[100.,135.]):
                r=measure(source=db,assignments={},model_sha='a'*40)
            self.assertEqual(r['build_elapsed_seconds'],35)
            self.assertEqual(r['snapshot_issue_epoch'],T)
            self.assertEqual(r['selected_profile_at_finish']['immediate_actionable'],0)
            self.assertEqual(db.read_bytes(),before)
            self.assertFalse(r['production_changed'])
            with patch('research.publication_snapshot_probe.prepare',return_value=snapshot),patch(
                    'research.publication_snapshot_probe.time.perf_counter',side_effect=[100.,110.]):
                r=measure(source=db,assignments={},model_sha='a'*40)
            self.assertEqual(r['selected_profile_at_finish']['immediate_actionable'],1)
            self.assertEqual(r['strict_at_finish']['immediate_actionable'],0)
