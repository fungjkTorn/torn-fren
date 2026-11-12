import unittest

from services.projection_chain_lab_v3 import (
    V3Strategy,
    _calibrated_error_window,
    _depth_bias,
    _wilson_lower,
)


class ProjectionChainLabV3Tests(unittest.TestCase):
    def test_depth_bias_uses_only_prior_rows(self):
        prior = [{"signed_error_seconds": x} for x in [60, 120, 180, 240, 300]]
        self.assertEqual(_depth_bias(prior, "depth_all"), 180)
        self.assertEqual(_depth_bias([], "depth_all"), 0.0)

    def test_calibrated_window_needs_history(self):
        self.assertIsNone(_calibrated_error_window(
            [{"signed_error_seconds": 10}] * 7
        ))
        window = _calibrated_error_window(
            [{"signed_error_seconds": x} for x in range(-40, 60, 10)],
            coverage=0.80,
            recent_limit=None,
        )
        self.assertIsNotNone(window)
        self.assertLessEqual(window["lo"], window["hi"])

    def test_wilson_lower_is_conservative(self):
        self.assertLess(_wilson_lower(8, 10), 0.8)
        self.assertGreater(_wilson_lower(10, 10), 0.5)

    def test_strategy_name_is_explicit(self):
        s = V3Strategy("recent_regime", "all_median", "adaptive20", "depth_recent10")
        self.assertIn("recent_regime", s.name)
        self.assertIn("bias:depth_recent10", s.name)


if __name__ == "__main__":
    unittest.main()
