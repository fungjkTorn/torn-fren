"""Production collector isolation checks; no network or database required."""
import ast
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
POLLER = ROOT / "poller.py"


class PollerCollectorContractTests(unittest.TestCase):
    def test_collector_only_imports_and_interval(self):
        tree = ast.parse(POLLER.read_text(encoding="utf-8"))
        imported = {
            (node.module or "")
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        self.assertIn("services.stock_provider", imported)
        self.assertIn("services.history_service", imported)
        self.assertNotIn("services.prediction_v2_live", imported)
        self.assertNotIn("services.forecast_auditor", imported)
        self.assertNotIn("services.shadow_model_auditor", imported)
        self.assertFalse(any("ThreadPoolExecutor" in ast.dump(node)
                             for node in ast.walk(tree)))
        self.assertTrue(any(
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "POLL_INTERVAL_SECONDS"
                    for t in node.targets)
            and isinstance(node.value, ast.Constant)
            and node.value.value == 30
            for node in tree.body
        ))

    def _isolated_poller(self, export, heartbeat):
        events = []
        provider = types.ModuleType("services.stock_provider")
        provider.get_travel_export = lambda: events.append("fetch") or export
        history = types.ModuleType("services.history_service")
        history.save_all_snapshots = lambda value: events.append("save") or {}
        history.record_poll_heartbeat = (
            lambda success, **kwargs: events.append(("heartbeat", success, kwargs))
            or heartbeat
        )
        recovery = types.ModuleType("research.v38_gap_recovery")
        recovery.pending = lambda *args, **kwargs: None
        module = types.ModuleType("poller_collector_contract_isolated")
        module.__file__ = str(POLLER)
        with patch.dict(sys.modules, {
            "services.stock_provider": provider,
            "services.history_service": history,
            "research.v38_gap_recovery": recovery,
        }):
            exec(compile(POLLER.read_text(encoding="utf-8"), str(POLLER), "exec"),
                 module.__dict__)
        return module, events

    def test_successful_poll_records_success_after_save(self):
        module, events = self._isolated_poller({"source": "test"}, {})
        with patch.object(module.time, "sleep", side_effect=StopIteration):
            with self.assertRaises(StopIteration):
                module.run()
        self.assertEqual(events[0:2], ["fetch", "save"])
        self.assertEqual(events[2][0:2], ("heartbeat", True))

    def test_missing_provider_is_recorded_as_failure(self):
        module, events = self._isolated_poller(None, None)
        with patch.object(module.time, "sleep", side_effect=StopIteration):
            with self.assertRaises(StopIteration):
                module.run()
        self.assertEqual(events[0], "fetch")
        self.assertEqual(events[1][0:2], ("heartbeat", False))
        self.assertEqual(events[1][2]["source"], "none")


if __name__ == "__main__":
    unittest.main()
