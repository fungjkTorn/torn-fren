"""Opt-in two-Xanax V42 scheduling never changes default 16."""
import unittest
from unittest.mock import Mock

from research.v38_budgeted_runner import (
    V42_XANAX_ROSTER, V42_XANAX_ROUTES, PINNED_WORKERS, choose, run_tick,
)

NOW=1800000000


class XanaxScheduleTests(unittest.TestCase):
    def test_exact_canada_uk_generic_and_japan_remains_excluded(self):
        self.assertEqual(set(V42_XANAX_ROSTER), {"can:Xanax","uni:Xanax"})
        self.assertNotIn("jap:Xanax",V42_XANAX_ROUTES)
        self.assertEqual(len(PINNED_WORKERS),16)
        self.assertTrue(all(x=="research.v42_xanax_candidate_tick"
                            for x in V42_XANAX_ROUTES.values()))

    def test_routes_are_exclusively_opt_in(self):
        original=run_tick(stock_db="/nonexistent",
            sidecar_db="/nonexistent/sidecar.db",now=NOW)
        self.assertNotIn("can:Xanax",original["plan"]["execute"])
        expanded=run_tick(stock_db="/nonexistent",
            sidecar_db="/nonexistent/sidecar.db",now=NOW,with_xanax=True,
            max_jobs=18)
        self.assertEqual(len(expanded["plan"]["execute"]),18)
        self.assertIn("can:Xanax",expanded["plan"]["execute"])
        self.assertIn("uni:Xanax",expanded["plan"]["execute"])
        self.assertIn("jap:Xanax",expanded["plan"]["pending_specialists"])

    def test_default_cap_and_explicit_expanded_cap(self):
        with self.assertRaises(ValueError):
            run_tick(stock_db="/unused",sidecar_db="/unused",now=NOW,max_jobs=18)
        with self.assertRaises(ValueError):
            run_tick(stock_db="/unused",sidecar_db="/unused",now=NOW,
                     with_xanax=True,max_jobs=19)

    def test_route_choice_does_not_substitute_generic_for_japan(self):
        extended={**PINNED_WORKERS,**V42_XANAX_ROUTES}
        selection=choose({"jap:Xanax":{},**V42_XANAX_ROSTER},{},
                         now=NOW,limit=18,routes=extended)
        self.assertEqual(set(selection["execute"]),set(V42_XANAX_ROSTER))
        self.assertEqual(selection["pending_specialists"],["jap:Xanax"])

if __name__=="__main__":
    unittest.main()
