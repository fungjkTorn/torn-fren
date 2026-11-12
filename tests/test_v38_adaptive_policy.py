"""Scheduling semantics: never lower cadence for actionable plans."""
import unittest
from research.v38_adaptive_policy import next_due_seconds


class AdaptivePolicyTests(unittest.TestCase):
    def test_actionable_or_active_replans_five_minutes(self):
        self.assertEqual(next_due_seconds(worker_status="RESEARCH_PROPOSAL_ONLY",
                                          median_restock_seconds=864000),300)
        self.assertEqual(next_due_seconds(worker_status="NO_RECOMMENDATION",
                                          active=True,median_restock_seconds=864000),300)

    def test_changed_stock_immediately_returns_to_five_minutes(self):
        self.assertEqual(next_due_seconds(worker_status="NO_RECOMMENDATION",
                                          stock_changed=True,
                                          median_restock_seconds=172800),300)

    def test_cold_and_day_scale_items_are_slow(self):
        self.assertEqual(next_due_seconds(worker_status="NO_RECOMMENDATION"),1800)
        self.assertEqual(next_due_seconds(worker_status="NO_RECOMMENDATION",
                                          median_restock_seconds=172800),3600)
        self.assertEqual(next_due_seconds(worker_status="WORKER_TIMEOUT"),300)


if __name__=="__main__":
    unittest.main()
