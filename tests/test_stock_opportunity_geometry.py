"""Exact-opportunity backtest safeguards; no future oracle in production."""
import unittest
from services.stock_opportunity_geometry import (
    Interval,observed_intervals,earliest_reachable_hindsight,grid_seconds_from_past_lifetimes,
)

class Tests(unittest.TestCase):
    def test_5_min_window_missed_at_15_min_grid(self):
        w=[Interval(3470,3570)]
        self.assertIsNotNone(earliest_reachable_hindsight(
            0,1800,w,[],max_wait_seconds=7200,grid_seconds=60))
        self.assertIsNone(earliest_reachable_hindsight(
            0,1800,w,[],max_wait_seconds=7200,grid_seconds=900))

    def test_10_second_grace(self):
        w=[Interval(3600,3601)]
        self.assertEqual(earliest_reachable_hindsight(
            0,1780,w,[],max_wait_seconds=7200,
            grace_seconds=10,grid_seconds=10),1810)
        self.assertIsNone(earliest_reachable_hindsight(
            0,1780,w,[],max_wait_seconds=7200,
            grace_seconds=0,grid_seconds=900))

    def test_gap_censorship(self):
        w=observed_intervals([0,100,200,300],[0,40,40,0],[(150,170)],30)
        self.assertEqual(w,[Interval(100,150),Interval(200,300)])
        self.assertIsNone(earliest_reachable_hindsight(
            0,160,w,[(150,170)],max_wait_seconds=300))

    def test_available_now_and_11_hour_restock(self):
        self.assertEqual(earliest_reachable_hindsight(
            100,500,[Interval(0,5000)],[],max_wait_seconds=1200),100)
        self.assertEqual(earliest_reachable_hindsight(
            0,7200,[Interval(11*3600,11*3600+500)],[],
            max_wait_seconds=43200),11*3600-7200-10)

    def test_full_observation_required(self):
        self.assertIsNone(earliest_reachable_hindsight(
            0,1800,[Interval(3600,4000)],[],max_wait_seconds=7200,
            last_observation_timestamp=5000))

    def test_qualified_stock_not_necessarily_restock(self):
        self.assertEqual(observed_intervals(
            [0,100,110,120,180],[29,30,31,35,29],[],30),
            [Interval(100,110),Interval(110,120),Interval(120,180)])

    def test_past_only_grid_policy(self):
        self.assertEqual(grid_seconds_from_past_lifetimes([400,500])["grid_seconds"],60)
        for x,expected in [([40,60,80],30),([200,220,240],60),
                           ([600,650,700],120),([1200,1300,1400],300)]:
            self.assertEqual(grid_seconds_from_past_lifetimes(x)["grid_seconds"],expected)

    def test_invalid_args(self):
        with self.assertRaises(ValueError):Interval(100,100)
        with self.assertRaises(ValueError):observed_intervals([3,2],[30,40],[],30)
        with self.assertRaises(ValueError):earliest_reachable_hindsight(
            0,50,[],[],grid_seconds=0)

if __name__=="__main__":
    unittest.main()
