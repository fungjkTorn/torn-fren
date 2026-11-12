import unittest

from research.causal_policy_selector import CausalPolicySelector


class SelectorTests(unittest.TestCase):
    def test_only_matured_prior_trips_train_and_selection_changes_after_evidence(self):
        selector=CausalPolicySelector(('base','expert'),'base')
        clock=[1000];calls=[]
        def score(arrival):
            self.assertGreaterEqual(clock[0],arrival+190)
            calls.append(arrival)
            return ('SUCCESS' if arrival%300==210 else 'FAILURE'),'fixture',None
        for tick in range(350):
            issued=1000+tick*300;clock[0]=issued
            selector.update(issued,{'base':{'estimated_departure_epoch':issued},
                                    'expert':{'estimated_departure_epoch':issued+10}},
                            poll_age=0,flight_seconds=100,score=score)
            winner,evidence=selector.select()
            if evidence['training_cohorts']<24:
                self.assertEqual(winner,'base')
        self.assertEqual(winner,'expert')
        self.assertTrue(calls)
        self.assertIsNone(evidence['calibrated_success_probability'])

    def test_plans_replace_expire_and_abstentions_remain_in_training(self):
        selector=CausalPolicySelector(('base','expert'),'base')
        for tick in range(99):
            issued=1000+tick*300
            selector.update(issued,{'base':{'estimated_departure_epoch':issued+300},
                                    'expert':{'estimated_departure_epoch':issued+200}},
                            poll_age=0,flight_seconds=100,
                            score=lambda t:self.fail('expired or replaced plans must not execute'))
        self.assertTrue(selector.completed)
        self.assertTrue(all(s['outcome']=='ABSTAIN' for s in selector.completed[0]['experts'].values()))
        self.assertEqual(selector.select()[0],'base')

    def test_invalid_roster_or_issue_order_rejected(self):
        with self.assertRaises(ValueError):CausalPolicySelector(('x',),'base')
        selector=CausalPolicySelector(('base',),'base')
        kwargs=dict(poll_age=0,flight_seconds=100,score=lambda t:('SUCCESS','fixture',None))
        with self.assertRaises(ValueError):selector.update(1000,{},**kwargs)
        selector.update(1000,{'base':{'estimated_departure_epoch':None}},**kwargs)
        with self.assertRaises(ValueError):selector.update(1600,{'base':{'estimated_departure_epoch':None}},**kwargs)


if __name__=='__main__':unittest.main()
