"""Active final-pair publisher's public host API must retain its opt-in policy.

The specialist model source is maintained in the *private* reviewed overlay.
This regression only checks the shared, public publisher interface; it never
imports research-only model data or executes the VM publisher.
"""
import inspect
import unittest

from services.first_release_live import publish
from services.first_release_schedule import build_first_release_decision


class FinalPairInterfaceContract(unittest.TestCase):
    def test_cohort_opt_in_is_explicit_and_off_by_default(self):
        sig = inspect.signature(publish)
        self.assertIn("current_stock_leave_now", sig.parameters)
        self.assertIs(sig.parameters["current_stock_leave_now"].default, False)
        self.assertIn("item_runner", sig.parameters)

    def test_staged_publisher_keeps_next_six_policy_and_accepts_final_pair(self):
        text = inspect.getsource(publish)
        self.assertIn("next_six_cohort or current_stock_leave_now", text)
        self.assertIn("current_stock_leave_now=", text)
        sig = inspect.signature(build_first_release_decision)
        self.assertIn("current_stock_leave_now", sig.parameters)
        self.assertIs(sig.parameters["current_stock_leave_now"].default, False)


if __name__ == "__main__":
    unittest.main()
