import unittest

from research.v164_evidence_routed_earliest_restock import (
    ROUTES, _clean_windows, _earliest_reachable_window,
)


class V164EarliestReachableTests(unittest.TestCase):
    def test_exact_24_routes_and_japan_abstains(self):
        self.assertEqual(24, len(ROUTES))
        self.assertIsNone(ROUTES["jap:Xanax"]["primary"])

    def test_clean_window(self):
        rows=[
            (900,0,"p"),(1100,40,"p"),(1500,20,"p"),
            (1900,45,"p"),(2500,0,"p"),
        ]
        self.assertEqual(
            [(1100,1500,"p"),(1900,2500,"p")],
            _clean_windows(rows,[],3000),
        )

    def test_current_stock_is_not_called_future_restock(self):
        rows=[(900,50,"p"),(1200,20,"p")]
        r=_earliest_reachable_window(rows,[],1000,600,3000)
        self.assertEqual("CURRENT_STOCK_ALREADY_GE30",r["status"])

    def test_first_future_restock_reachable_exactly(self):
        rows=[(900,0,"p"),(1200,40,"p"),(1800,0,"p")]
        r=_earliest_reachable_window(rows,[],1000,600,3000)
        self.assertEqual("EARLIEST_REACHABLE_FOUND",r["status"])
        self.assertEqual(1200,r["restock"])
        self.assertEqual(1000,r["oracle_earliest_departure"])
        self.assertEqual(1600,r["oracle_earliest_arrival"])

    def test_skip_unreachable_short_window_and_target_next(self):
        rows=[
            (900,0,"p"),
            (1100,40,"p"),(1500,0,"p"),   # arrival at 1600 would miss
            (2000,40,"p"),(2800,0,"p"),
        ]
        r=_earliest_reachable_window(rows,[],1000,600,3000)
        self.assertEqual("EARLIEST_REACHABLE_FOUND",r["status"])
        self.assertEqual(2000,r["restock"])
        self.assertEqual(1400,r["oracle_earliest_departure"])
        self.assertEqual(2000,r["oracle_earliest_arrival"])

    def test_gap_restock_not_invented(self):
        rows=[(900,0,"p"),(1200,40,"p"),(1800,0,"p")]
        self.assertEqual([], _clean_windows(rows,[(1000,1300)],3000))


if __name__=="__main__":
    unittest.main()
