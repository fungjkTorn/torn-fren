"""Fail-closed champion UI presentation must not imply verified live accuracy."""
import unittest
from web.v41_champion_cache import _present, read_snapshots


class ChampionCacheTests(unittest.TestCase):
    def _row(self):
        return dict(item_key='arg:Monkey Plushie', computed_at=1000, stock_as_of=990,
                    valid_until=1300, departure=1150, arrival=1200, executed=1,
                    status='RESEARCH_PROPOSAL_ONLY', model_family='test', model_config='safe')

    def test_verified_research_snapshot_remains_experimental(self):
        result = _present(self._row(), now=1100, live_heartbeat=1099)
        self.assertEqual(result['status'], 'RESEARCH_PROPOSAL_ONLY')
        self.assertTrue(result['actionable'])
        self.assertFalse(result['prediction_accuracy_verified'])
        self.assertTrue(result['experimental'])

    def test_stale_or_unverified_collector_suppresses_departure(self):
        for heartbeat in (None, 900, 1101):
            with self.subTest(heartbeat=heartbeat):
                result = _present(self._row(), now=1100, live_heartbeat=heartbeat)
                self.assertFalse(result['actionable'])
                self.assertIsNone(result['departure'])

    def test_missing_snapshot_file_fails_closed(self):
        result = read_snapshots('/path/does/not/exist.sqlite', now=1100, key='arg:Monkey Plushie')
        self.assertFalse(result['actionable'])
        self.assertEqual(result['status'], 'SNAPSHOT_CACHE_UNAVAILABLE')


if __name__ == '__main__':
    unittest.main()
