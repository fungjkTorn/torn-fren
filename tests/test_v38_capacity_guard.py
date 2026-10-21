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

    def test_opt_in_only_for_autonomous_unparameterized_private_worker(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"TORN_FREN_V38_IDLE_ADMISSION": "1"}):
            with patch("research.v38_idle_admission.inspect",
                       return_value={"allowed": True, "admission_mode": "measured_linux_idle_psi"}) as measured:
                self.assertTrue(inspect()["allowed"])
                measured.assert_called_once_with()
                # Explicitly parameterized tests/probes retain legacy limit.
                self.assertFalse(inspect(load_1m=2.4,slots=2)["allowed"])

    def test_unsafe_threshold_refused(self):
        with self.assertRaises(ValueError):
            inspect(load_1m=0,slots=1,max_load_per_slot=1.5)


if __name__=="__main__":
    unittest.main()
