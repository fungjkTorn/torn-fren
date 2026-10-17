import unittest
from unittest.mock import patch
from research.japan_xanax.coverage_challengers import support_at,combine,run
from research.japan_xanax.renewal_shadow import History


def plans(primary=None,rate=60,quantity=120):
    return {k:dict(departure=v) for k,v in [('sequence_blocks_peak',primary),('rate_current_quarter',rate),('quantity_blocks_peak',quantity)]}


def curves(seq=.4,pair=.3):
    return {k:dict(delays=[0,60,120],support=v) for k,v in [('sequence_blocks',[.1,seq,.5]),('paired_recent',[.1,pair,.5])]}


class CoverageTests(unittest.TestCase):
    def test_fallback_preserves_primary_and_uses_only_supported_abstentions(self):
        a=combine(plans(primary=30),curves(),0)
        self.assertTrue(all(a[m]==30 for m in a if m.startswith('fallback_')))
        a=combine(plans(),curves(),0)
        self.assertEqual(a['fallback_rate_seq25'],60);self.assertEqual(a['fallback_rate_agreement25'],60)
        self.assertIsNone(a['fallback_rate_agreement40']);self.assertEqual(a['fallback_quantity_peak'],120)
        a=combine(plans(rate=30000),curves(),0)
        self.assertIsNone(a['fallback_rate_seq25'])

    def test_support_is_conservative_and_never_extrapolated(self):
        c=curves()['sequence_blocks']
        self.assertEqual(support_at(c,30),.1);self.assertEqual(support_at(c,60),.4)
        self.assertEqual(support_at(c,121),0);self.assertEqual(support_at(None,60),0)
        a=combine(plans(),{},0)
        self.assertTrue(all(a[m] is None for m in a if m!='fallback_quantity_peak'))

    def test_curve_export_does_not_change_existing_predictions(self):
        from test_renewal_shadow import rows,T
        h=History(lambda a,b:False)
        for row in rows():h.add(row)
        diagnostics={};a=h.plans(T,poll_age=0);b=h.plans(T,poll_age=0,diagnostics=diagnostics)
        self.assertEqual(a,b);self.assertEqual(len(diagnostics),3)
        self.assertTrue(all(0<=v<=1 for c in diagnostics.values() for v in c['support']))
        a=combine({k:dict(departure=None) for k in plans()},diagnostics,T)
        self.assertTrue(all(v is None or T<=v<=T+28800 for v in a.values()))

    def test_six_day_report_has_fixed_nonoverlapping_halves_and_no_promotion(self):
        class Evidence:
            def score(self,arrival):return ('SUCCESS','TEST',None)
        end=1791956400;cutoff=end+100000
        data=([],list(range(end-7*86400,cutoff+1,30)),lambda a,b:False,Evidence(),cutoff)
        with patch('research.japan_xanax.coverage_challengers.source_data',return_value=data):
            result=run('unused',model_sha='a'*40,issue_end=end)
        a=result['reports']['earlier_three_days'];b=result['reports']['reserved_later_three_days']
        self.assertEqual(a['issue_end']+300,b['issue_start'])
        self.assertTrue(all(v['starts']==864 for v in a['policies'].values()))
        self.assertTrue(all(v['starts']==864 for v in b['policies'].values()))
        self.assertEqual(result['reports']['all_six_days']['policies']['leave_now_control']['starts'],1728)
        self.assertFalse(result['automatic_promotion'])


if __name__=='__main__':unittest.main()
