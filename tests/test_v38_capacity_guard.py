"""VM admission thresholds are tested independently of actual runner load."""
import unittest
from research.v38_capacity_guard import inspect


class CapacityGuardTests(unittest.TestCase):
    def test_supplied_oracle_single_core_metrics_block(self):
        actual=inspect(load_1m=4.50,slots=1)
        self.assertFalse(actual["allowed"])
        self.assertEqual(actual["normalized_load"],4.5)
        self.assertEqual(actual["cpu_slots"],1)

    def test_idle_oracle_is_eligible_not_a_deployment_approval(self):
        self.assertTrue(inspect(load_1m=0.35,slots=1)["allowed"])

    def test_multicore_threshold_scales(self):
        self.assertFalse(inspect(load_1m=3.7,slots=4)["allowed"])
        self.assertTrue(inspect(load_1m=2.0,slots=4)["allowed"])

    def test_unsafe_threshold_refused(self):
        with self.assertRaises(ValueError):
            inspect(load_1m=0,slots=1,max_load_per_slot=1.5)


if __name__=="__main__":
    unittest.main()
