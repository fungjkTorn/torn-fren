import unittest
from research.departure_reconfirmation import evaluate


class ReconfirmationTests(unittest.TestCase):
    def check(self, plans, cutoff=10000):
        self.arrivals=[]
        def score(arrival):
            self.arrivals.append(arrival)
            return 'SUCCESS','fixture',None
        return evaluate(plans,cutoff=cutoff,flight_seconds=100,score=score)

    def test_due_plan_replaced_by_latest_abstention(self):
        r=self.check([(1000,1300,0),(1300,None,0),(1600,1610,0)])
        self.assertEqual(self.arrivals,[1710])
        self.assertEqual(r['SUCCESS'],1)
        self.assertEqual(r['wait_seconds_sum'],610)

    def test_expired_source_cannot_execute_and_future_tail_is_pending(self):
        r=self.check([(1000,1100,100),(1300,None,None)],cutoff=1400)
        self.assertFalse(self.arrivals)
        self.assertEqual(r['expired_before_departure_rechecks'],1)
        self.assertEqual(r['PENDING'],1)

    def test_mature_no_plan_is_abstention_not_arrival_failure(self):
        r=self.check([(1000,None,0)],cutoff=40000)
        self.assertEqual(r['ABSTAIN'],1)
        self.assertEqual(r['scored'],0)


if __name__=='__main__': unittest.main()
