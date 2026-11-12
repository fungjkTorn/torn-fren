import unittest
from research.nearest_stock_boundary_misses import classify


class BoundaryTests(unittest.TestCase):
    def test_nearest_side_and_tie(self):
        rows=[(1,100,'a'),(60,0,'a'),(840,100,'a')]
        q={'pre_quantity':0,'post_quantity':0}
        self.assertEqual('LATE',classify(420,q,rows,[])['classification'])
        self.assertEqual(6,classify(420,q,rows,[])['minutes_after_zero'])
        self.assertEqual(7,classify(420,q,rows,[])['minutes_before_restock'])
        self.assertEqual('EARLY',classify(480,q,rows,[])['classification'])
        self.assertEqual('TIE',classify(450,q,rows,[])['classification'])

    def test_positive_stock_missing_boundary_and_provider_conflict(self):
        rows=[(1,100,'a'),(60,0,'a'),(840,100,'a')]
        self.assertEqual('POSITIVE_STOCK_AT_OR_BELOW_30',classify(420,{'pre_quantity':30,'post_quantity':20},rows,[])['classification'])
        self.assertEqual('UNKNOWN',classify(420,{'pre_quantity':0,'post_quantity':0},rows[:-1],[])['classification'])
        self.assertEqual('UNKNOWN',classify(420,{'pre_quantity':0,'post_quantity':0},rows,[(100,200)])['classification'])


if __name__=='__main__':unittest.main()
