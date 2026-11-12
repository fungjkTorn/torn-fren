"""Causal freshness evidence regression checks for production helper."""
import unittest
from services.provider_freshness import ProviderFreshness


class ProviderFreshnessTests(unittest.TestCase):
    def test_fresh_receipt_requires_reported_upstream_clock(self):
        self.assertFalse(ProviderFreshness([(1000, 'yata', None, 'REPORTED')]).fresh(1010))
        self.assertFalse(ProviderFreshness([(1000, 'yata', 990, 'UNKNOWN')]).fresh(1010))
        self.assertTrue(ProviderFreshness([(1000, 'yata', 990, 'REPORTED')]).fresh(1010))

    def test_old_and_future_receipts_cannot_authorize_freshness(self):
        p = ProviderFreshness([(800, 'yata', 800, 'REPORTED')])
        self.assertFalse(p.fresh(1000))
        p = ProviderFreshness([(1050, 'yata', 1040, 'REPORTED')])
        self.assertFalse(p.fresh(1000))

    def test_latest_provider_receipt_wins(self):
        p = ProviderFreshness([
            (1000, 'yata', 995, 'REPORTED'),
            (1008, 'yata', None, 'UNAVAILABLE'),
            (1002, 'prometheus', 1001, 'REPORTED'),
        ])
        self.assertEqual(len(p.evidence(1010)), 1)
        self.assertEqual(p.evidence(1010)[0][1], 'prometheus')


if __name__ == '__main__':
    unittest.main()
