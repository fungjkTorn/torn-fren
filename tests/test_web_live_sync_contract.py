"""Review-branch, offline website safety and compatibility checks."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WebSyncContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = (ROOT / "web/static/index.html").read_text(encoding="utf-8")
        cls.app = (ROOT / "web/app.py").read_text(encoding="utf-8")
        cls.bridge = (ROOT / "web/first_release_bridge.py").read_text(encoding="utf-8")
        cls.admin = (ROOT / "web/static/admin.html").read_text(encoding="utf-8")

    def test_old_v2_only_available_by_explicit_ten_minute_action(self):
        self.assertIn('id="legacyV2Button"', self.index)
        self.assertIn("legacyV2Button.addEventListener(\"click\"", self.index)
        self.assertIn("10 * 60 * 1000", self.index)
        self.assertIn("&legacy_v2=true", self.index)
        self.assertIn("legacyV2UntilMs > Date.now()", self.index)
        self.assertIn("legacy_v2: bool = False", self.app)
        self.assertIn("legacy_v2_backup_available", self.app)

    def test_stock_graph_never_recommends_on_stale_forecast(self):
        self.assertIn("function departureGuidanceBlock(", self.index)
        self.assertIn("predictionRefreshFailed", self.index)
        self.assertIn("RECHECK REQUIRED", self.index)
        self.assertIn("Collector evidence is stale or unknown", self.index)

    def test_web_keeps_current_navigation_and_status(self):
        for path in ("/experimental", "/travel-decisions"):
            self.assertIn(path, self.index)
        self.assertIn("/site_shell.js", self.index)
        self.assertIn("source freshness", self.admin.lower())
        self.assertIn("escape(", self.admin)

    def test_bridge_has_all_24_cohort_rosters(self):
        for token in ("CHALLENGER_ROSTER", "NEXT_SIX_ROSTER", "FINAL_PAIR_ROSTER",
                      "'next_six'", "'final_pair'"):
            self.assertIn(token, self.bridge)
        self.assertIn("install_first_release(app)", self.app)


if __name__ == "__main__":
    unittest.main()
