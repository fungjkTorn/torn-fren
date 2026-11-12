import unittest
from research.departure_reconfirmation import evaluate,evaluate_utc,evaluate_all_starts,evaluate_committed,compare_cohorts


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
        self.assertEqual(r['chronological_start_day_slices'][0]['SUCCESS'],1)
        self.assertEqual(r['chronological_start_day_slices'][0]['starts'],1)

    def test_expired_source_cannot_execute_and_future_tail_is_pending(self):
        r=self.check([(1000,1100,100),(1300,None,None)],cutoff=1400)
        self.assertFalse(self.arrivals)
        self.assertEqual(r['expired_before_departure_rechecks'],1)
        self.assertEqual(r['PENDING'],1)

    def test_mature_no_plan_is_abstention_not_arrival_failure(self):
        r=self.check([(1000,None,0)],cutoff=40000)
        self.assertEqual(r['ABSTAIN'],1)
        self.assertEqual(r['scored'],0)

    def test_utc_grid_does_not_move_with_a_snapshot_prefix(self):
        plans=[(t,t,0) for t in range(300,10801,300)]
        kw=dict(cutoff=100000,flight_seconds=100,score=lambda t:('SUCCESS','fixture',None))
        left=[];right=[]
        a=evaluate_utc(plans,cohorts=left,**kw)
        b=evaluate_utc(plans[3:],cohorts=right,**kw)
        self.assertEqual(left,right)
        self.assertEqual([c['start'] for c in left],[3600,7200,10800])
        self.assertEqual(a['SUCCESS'],b['SUCCESS'])

    def test_all_offsets_expose_a_favorable_single_start_phase(self):
        plans=[(t,t,0) for t in range(300,10801,300)]
        kw=dict(cutoff=100000,flight_seconds=100,
                score=lambda t:('SUCCESS' if t%3600==400 else 'FAILURE','fixture',None))
        self.assertEqual(evaluate(plans,**kw)['success_fraction'],1.)
        cohorts=[];r=evaluate_all_starts(plans,cohorts=cohorts,**kw)
        self.assertEqual(r['starts'],36)
        self.assertEqual(r['SUCCESS'],3)
        self.assertEqual(len({c['start'] for c in cohorts}),36)
        self.assertEqual(len(r['offsets']),12)
        self.assertEqual(evaluate_all_starts(plans,start_before=7200,**kw)['starts'],24)

    def test_commitment_freezes_first_target_but_refreshes_health(self):
        plans=[(1000,1600,0),(1300,1900,0),(1600,None,0),(1900,1900,0)]
        arrivals=[]
        def score(t):
            arrivals.append(t)
            return ('SUCCESS' if t==1700 else 'FAILURE'),'fixture',None
        kw=dict(cutoff=40000,flight_seconds=100,score=score,start_before=1000)
        frozen=[];r=evaluate_committed(plans,cohorts=frozen,**kw)
        self.assertEqual(arrivals,[1700]);self.assertEqual(r['SUCCESS'],1)
        replanned=[];evaluate_all_starts(plans,cohorts=replanned,**kw)
        self.assertEqual(compare_cohorts(replanned,frozen)['challenger_only_success'],1)
        stale=plans[:2]+[(1600,None,181)]+plans[3:]
        arrivals.clear();r=evaluate_committed(stale,**kw)
        self.assertFalse(arrivals)
        self.assertEqual(r['cancelled_stale_departure_evidence'],1)
        self.assertEqual(r['ABSTAIN'],1)

    def test_commitment_unknown_pending_and_wait_limit_remain_visible(self):
        kw=dict(flight_seconds=100,score=lambda t:('UNKNOWN','fixture',None),start_before=1000)
        plans=[(1000,1600,0),(1300,None,0),(1600,None,0)]
        r=evaluate_committed(plans,cutoff=1700,**kw)
        self.assertEqual(r['UNKNOWN'],1);self.assertEqual(r['scored'],0)
        self.assertEqual(evaluate_committed(plans[:2],cutoff=1400,**kw)['PENDING'],1)
        self.assertEqual(evaluate_committed([(1000,40000,0)],cutoff=50000,**kw)['ABSTAIN'],1)


if __name__=='__main__': unittest.main()
