import unittest
from research.fixed_roster_release_check import Cohorts,eligible,WAIT


class ReleaseCheckTests(unittest.TestCase):
    def test_new_advice_replaces_future_plan_and_boundary_uses_new_issue(self):
        c=Cohorts(['native'],starts=(0,));c.begin(0)
        c.advance(0,{'native':300},0)
        self.assertEqual(len(c.active),1)
        c.begin(300);c.advance(300,{'native':900},0)
        self.assertEqual(len(c.active),1)
        c.begin(600);c.advance(600,{'native':615},0)
        self.assertEqual(c.departed[0]['departure'],615)

    def test_source_expires_at_departure_and_deadline_is_absolute(self):
        self.assertFalse(eligible(300,315,170,1000))
        self.assertFalse(eligible(300,315,0,310))
        self.assertTrue(eligible(300,315,165,1000))

    def test_truth_used_only_after_schedule_resolves_and_no_dropped_cohorts(self):
        c=Cohorts(['native','rate'],starts=(0,));c.begin(0)
        c.advance(0,{'native':15},0)
        c.begin(WAIT+300)
        class E:
            def score(self,t):return 'UNKNOWN',None,None
        r=c.score(E(),10)
        self.assertEqual(len(r),2)
        self.assertEqual({x['outcome'] for x in r},{'UNKNOWN','ABSTAIN'})

    def test_immature_truth_rejected_not_counted_as_failure(self):
        c=Cohorts(['native'],starts=(0,));c.begin(0);c.advance(0,{'native':15},0)
        class E:
            def score(self,t):return 'PENDING',None,None
        with self.assertRaises(ValueError):c.score(E(),10)


if __name__=='__main__':unittest.main()
