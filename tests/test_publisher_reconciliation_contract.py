"""Review-branch regression guard: publisher and schedule must preserve both cohorts.

Static contract checks deliberately avoid collector/DB/network imports. Runtime and
end-to-end model validation are independent release gates.
"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def tree(path):
    return ast.parse((ROOT / path).read_text(encoding="utf-8"))


def function(root, name):
    matches = [node for node in ast.walk(root)
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if len(matches) != 1:
        raise AssertionError(f"Expected one function {name}, got {len(matches)}")
    return matches[0]


def args(func):
    return {item.arg for item in func.args.args + func.args.kwonlyargs}


class PublisherCompatibilityTests(unittest.TestCase):
    def test_live_publisher_accepts_two_cohorts(self):
        source = ROOT / "services/first_release_live.py"
        node = tree("services/first_release_live.py")
        self.assertIn("next_six_cohort", args(function(node, "publish")))
        self.assertIn("challenger_cohort", args(function(node, "publish")))
        source_text = source.read_text(encoding="utf-8")
        for term in ("--next-six-cohort", "--challenger-cohort",
                     "STINGRAY_PRESERVE_VALID_V1", "monkey_model_policy",
                     "quantity >= 30 at calculated landing"):
            self.assertIn(term, source_text)

    def test_schedule_preserves_minute_refinement_and_next_six_features(self):
        node = tree("services/first_release_schedule.py")
        self.assertTrue({"current_stock_leave_now", "allow_minute_refinement"}.issubset(
            args(function(node, "build_first_release_decision"))))
        self.assertTrue({"current_stock_leave_now", "refine_minute",
                         "forecast_transform", "event_forecaster"}.issubset(
            args(function(node, "forecast_first_release_item"))))
        self.assertIn("refine_minute", args(function(node, "native_timing_choice")))
        text = (ROOT / "services/first_release_schedule.py").read_text(encoding="utf-8")
        self.assertIn("reviewed_foundation", text)

    def test_next_six_entry_has_matching_publish_interface(self):
        node = tree("services/next_six_live.py")
        publishes = [n for n in ast.walk(node) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Name) and n.func.id == "publish"]
        self.assertEqual(len(publishes), 1)
        keys = {kw.arg for kw in publishes[0].keywords}
        self.assertIn("next_six_cohort", keys)
        self.assertIn("model_roster", keys)
        roster = tree("services/forward_beta_roster.py")
        names = {target.id for n in ast.walk(roster) if isinstance(n, ast.Assign)
                 for target in n.targets if isinstance(target, ast.Name)}
        self.assertIn("NEXT_SIX_MODELS", names)
        self.assertIn("CHALLENGER_MODELS", names)


if __name__ == "__main__":
    unittest.main()
