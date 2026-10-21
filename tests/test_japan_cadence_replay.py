import unittest
from research.japan_xanax.cadence_replay import evaluate


def r(issued,dep,published=None):return dict(issued=issued,published=issued+15 if published is None else published,source_cutoff=issued,departure=dep)


class CadenceTests(unittest.TestCase):
    def score(self,arrival):return ('SUCCESS','TEST',None)

    def test_new_advice_cancels_old_target_only_after_publication(self):
        v=evaluate([r(0,120),r(60,None)], [0], cutoff=100000,score=self.score)
        self.assertEqual(v.get('departed',0),0)
        v=evaluate([r(0,60),r(60,None)], [0], cutoff=100000,score=self.score)
        self.assertEqual(v.get('departed',0),1)

    def test_more_frequent_recheck_can_refresh_health_without_blind_commitment(self):
        slow=evaluate([r(0,240),r(300,None)],[0],cutoff=100000,score=self.score)
        fast=evaluate([r(0,240),r(60,240),r(120,240),r(180,240),r(240,None)],[0],cutoff=100000,score=self.score)
        self.assertEqual(slow.get('departed',0),0);self.assertEqual(fast.get('departed',0),1)
        self.assertEqual(fast['success_fraction'],1)

    def test_unchanged_start_grid_and_incomplete_followup_is_not_failure(self):
        v=evaluate([r(0,None),r(60,None)],[0,60],cutoff=100000,score=self.score)
        self.assertEqual(v['starts'],2);self.assertEqual(v['PENDING'],2)
        self.assertIsNone(v['success_fraction'])
        v=evaluate([r(0,15)],[0],cutoff=0,score=self.score)
        self.assertEqual(v.get('departed',0),0)


if __name__=='__main__':unittest.main()
