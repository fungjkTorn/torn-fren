import unittest
from research.japan_xanax.departure_stability import RecheckedTarget


def curve(support=.5):return dict(delays=[0,60,120,180,240,300,360,420,480,540,600,660,720],support=[support]*13)


class StabilityTests(unittest.TestCase):
    def test_supported_old_target_is_retained_when_new_model_moves_later(self):
        t=RecheckedTarget(.3)
        self.assertEqual(t.choose(0,600,curve(),0),600)
        self.assertEqual(t.choose(300,900,curve(),0),600)
        self.assertEqual(t.counts['retained_after_current_support_recheck'],1)

    def test_never_keeps_unsupported_expired_or_stale_target(self):
        t=RecheckedTarget(.3);t.choose(0,600,curve(),0)
        self.assertEqual(t.choose(300,900,curve(.1),0),900)
        self.assertIsNone(t.choose(600,1200,curve(),170));self.assertIsNone(t.target)
        t.choose(600,900,curve(),0)
        self.assertEqual(t.choose(900,1200,curve(),0),1200)
        self.assertIsNone(t.choose(1200,1500,None,0))

    def test_never_extrapolates_support_or_retains_old_advice_without_curve(self):
        t=RecheckedTarget(.3);t.choose(0,600,curve(),0)
        self.assertIsNone(t.choose(300,None,dict(delays=[0,60],support=[1,1]),0))
        self.assertIsNone(t.choose(600,30000,curve(),0))


if __name__=='__main__':unittest.main()
