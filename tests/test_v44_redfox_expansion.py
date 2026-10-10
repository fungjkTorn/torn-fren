"""Guard the explicit 19th Red Fox champion opt-in; preserve 18 and 16."""
import unittest
from research.v38_budgeted_runner import (
    RED_FOX_KEY, RED_FOX_WORKER, run_tick, PINNED_WORKERS,
)

NOW=1791610000


class RedFoxActivationTests(unittest.TestCase):
    def plan(self, **kwargs):
        return run_tick(
            stock_db="/nonexistent/collector.db",
            sidecar_db="/nonexistent/private.db", now=NOW, **kwargs,
        )

    def test_default_and_eighteen_stay_frozen(self):
        default=self.plan(max_jobs=16)
        self.assertEqual(len(default["plan"]["execute"]),16)
        self.assertIn(RED_FOX_KEY,default["plan"]["pending_specialists"])
        existing=self.plan(max_jobs=18,with_xanax=True)
        self.assertEqual(len(existing["plan"]["execute"]),18)
        self.assertIn(RED_FOX_KEY,existing["plan"]["pending_specialists"])

    def test_nineteenth_route_is_exact_original_adapter(self):
        expanded=self.plan(max_jobs=19,with_xanax=True,with_redfox=True)
        self.assertEqual(len(expanded["plan"]["execute"]),19)
        self.assertIn(RED_FOX_KEY,expanded["plan"]["execute"])
        self.assertIn("can:Xanax",expanded["plan"]["execute"])
        self.assertIn("uni:Xanax",expanded["plan"]["execute"])
        self.assertIn("jap:Xanax",expanded["plan"]["pending_specialists"])
        self.assertEqual(RED_FOX_WORKER,"research.v38_red_fox_single_tick")
        self.assertNotIn(RED_FOX_KEY,PINNED_WORKERS)

    def test_only_current_expansion_can_use_nineteen(self):
        with self.assertRaises(ValueError):
            self.plan(max_jobs=19,with_xanax=True)
        with self.assertRaises(ValueError):
            self.plan(max_jobs=19)
        with self.assertRaises(ValueError):
            self.plan(max_jobs=17,with_redfox=True)
        with self.assertRaises(ValueError):
            self.plan(max_jobs=20,with_xanax=True,with_redfox=True)

    def test_no_source_or_sidecar_write_without_execute(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            side=Path(tmp)/"sidecar.db"
            result=run_tick(stock_db=Path(tmp)/"missing.db",
                            sidecar_db=side,now=NOW,max_jobs=19,
                            with_xanax=True,with_redfox=True)
            self.assertEqual(result["mode"],"PLAN_ONLY")
            self.assertFalse(side.exists())


if __name__=="__main__":
    unittest.main()
