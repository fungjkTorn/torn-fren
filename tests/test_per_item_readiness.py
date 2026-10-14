import copy
import unittest
from research.per_item_readiness import readiness


def study(rate=.93,latest=.93,coverage=.85,phases=30,wait=1000):
    return {'scored':1000,'SUCCESS':int(rate*1000),'proposals':1100,
        'proposal_fraction':coverage,'first_proposal_per_issue_phase':{'scored':phases},
        'chronological_day_slices':[{'success_fraction':latest}],
        'wait_seconds_sum':1100*wait,
        'replanned_hourly_starts':{'scored':150,'success_fraction':rate,'departure_coverage':coverage}}


class ReadinessTests(unittest.TestCase):
    def report(self,policies,matched=None):
        return {'items':{'mex:Jaguar Plushie':{'policies':policies,'matched_v166_comparisons':matched or {}}}}

    def test_low_coverage_small_phase_sample_and_bad_latest_day_do_not_pass(self):
        for kwargs in ({'coverage':.1},{'phases':2},{'latest':.5}):
            r=readiness(self.report({'v166_all_history':study(**kwargs)}))
            self.assertEqual(r['rows'][0]['status'],'MORE_RESEARCH_REQUIRED')
            self.assertIsNone(r['rows'][0]['research_candidate'])

    def test_prefer_earlier_supported_candidate_and_never_promote(self):
        policies={'v166_all_history':study(wait=1000),'quarter_buffer_all_history':study(rate=.95,wait=2000)}
        matched={'quarter_buffer_all_history':{'matched_issues':900,'challenger_only_success':90,'v166_only_success':20}}
        r=readiness(self.report(policies,matched))
        self.assertEqual(r['rows'][0]['research_candidate']['policy'],'v166_all_history')
        self.assertFalse(r['automatic_model_promotion'])
        self.assertFalse(r['rows'][0]['production_model_changed'])

    def test_postponed_low_coverage_and_unscored_execution_cannot_pass(self):
        for values in ({'scored':0,'success_fraction':None,'departure_coverage':0},
                       {'scored':150,'success_fraction':1.,'departure_coverage':.3},
                       {'scored':150,'success_fraction':.7,'departure_coverage':1.}):
            v=study();v['replanned_hourly_starts']=values
            r=readiness(self.report({'v166_all_history':v}))
            self.assertEqual(r['rows'][0]['status'],'MORE_RESEARCH_REQUIRED')
        v=study();v.pop('replanned_hourly_starts')
        self.assertIsNone(readiness(self.report({'v166_all_history':v}))['rows'][0]['research_candidate'])

    def test_bad_matched_outcomes_exclude_candidate_and_input_unchanged(self):
        source=self.report({'quarter_buffer_all_history':study()}, {'quarter_buffer_all_history':{
            'matched_issues':900,'challenger_only_success':20,'v166_only_success':90}})
        before=copy.deepcopy(source)
        r=readiness(source)
        self.assertEqual(source,before)
        self.assertEqual(r['rows'][0]['status'],'MORE_RESEARCH_REQUIRED')
