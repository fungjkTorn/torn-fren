import unittest
from research.japan_xanax.target_trace import trace


def r(issue,dep,*,published=None,source=None):
    return dict(issued=issue,published=issue+15 if published is None else published,
        source_cutoff=issue if source is None else source,departure=dep,item_key='jap:Xanax',mode='test',status='TEST')


def counts(rows,asof=2000):return trace(rows,asof=asof)['items']['jap:Xanax']['test']


class TraceTests(unittest.TestCase):
    def test_distinguishes_withdrawn_postponed_and_advanced(self):
        self.assertEqual(counts([r(0,600),r(300,None)])['counts']['WITHDRAWN'],1)
        self.assertEqual(counts([r(0,600),r(300,900)])['counts']['POSTPONED'],1)
        self.assertEqual(counts([r(0,600),r(300,400)])['counts']['ADVANCED'],1)

    def test_reconfirmed_target_is_actionable_and_duplicate_issues_not_independent(self):
        v=counts([r(0,420),r(300,420)])
        self.assertEqual(v['counts']['TARGET_REACHED_WITH_VALID_RECORDED_ADVICE'],2)
        self.assertEqual(v['distinct_eligible_departures'],1)

    def test_stale_unpublished_and_expired_plans_are_not_departures(self):
        self.assertEqual(counts([r(0,200)])['counts']['SOURCE_EXPIRED_AT_TARGET'],1)
        self.assertEqual(counts([r(0,300)])['counts']['EXPIRED_WITHOUT_RECONFIRMATION'],1)
        self.assertEqual(counts([r(0,10,published=15)])['counts']['TARGET_ALREADY_PASSED_AT_PUBLICATION'],1)
        self.assertEqual(counts([r(0,600)],asof=200)['counts']['AWAITING_RECORDED_RECONFIRMATION'],1)
        self.assertEqual(counts([r(0,200)])['distinct_eligible_departures'],0)

    def test_later_unpublished_issue_does_not_cancel_current_advice(self):
        v=counts([r(0,180),r(170,None,published=190)])
        self.assertEqual(v['counts']['TARGET_REACHED_WITH_VALID_RECORDED_ADVICE'],1)
        self.assertEqual(v['distinct_eligible_departures'],1)

    def test_missing_source_clock_never_becomes_assumed_freshness(self):
        record=r(0,60);del record['source_cutoff']
        v=counts([record]);self.assertEqual(v['distinct_eligible_departures'],0)
        self.assertEqual(v['counts']['SOURCE_HEALTH_UNRECORDED'],1)


if __name__=='__main__':unittest.main()
