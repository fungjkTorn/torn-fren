from types import SimpleNamespace
import unittest
import numpy as np
from research.plushie_champions.common import recent_target_series


class ResolvedFeatureTests(unittest.TestCase):
    def context(self, windows):
        return SimpleNamespace(grid=np.array([201,499,500,501,901],float),
            timelines={('uni','Red Fox Plushie'):SimpleNamespace(windows=windows)})

    def test_low_duration_unavailable_until_next_restock_has_happened(self):
        ctx=self.context([(100,200,100),(500,600,100),(900,1000,100)])
        high,low=recent_target_series(ctx,'uni','Red Fox Plushie')
        self.assertTrue(np.all(np.isnan(low[:3])))
        self.assertEqual(low[3],300)
        self.assertEqual(low[4],300)
        self.assertEqual(high[0],100)

    def test_moving_unresolved_restock_cannot_change_prior_features(self):
        a=self.context([(100,200,100),(500,600,100),(900,1000,100)])
        b=self.context([(100,200,100),(800,850,50),(1200,1300,100)])
        x=recent_target_series(a,'uni','Red Fox Plushie')[1]
        y=recent_target_series(b,'uni','Red Fox Plushie')[1]
        np.testing.assert_equal(x[:3],y[:3])


if __name__=='__main__':unittest.main()
