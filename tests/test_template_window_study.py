import unittest
from types import SimpleNamespace
import numpy as np
from research.template_window_study import GuardedTimeline,nessie_choices,curve,plateau_choice
from research.plushie_champions.common import DAY,TemplatePlanner
from research.v46_fast_template import FastTemplatePlanner

T=1792255500


class TemplateStudyTests(unittest.TestCase):
    def test_prefix_prevents_future_provider_bounce_cleanup(self):
        rows=[(T-10,100,'a'),(T-5,0,'b'),(T+5,100,'a')]
        tl=GuardedTimeline(rows,[],'uni:Nessie Plushie',T)
        self.assertEqual(tl.vals([T])[1][0],0)
        with self.assertRaises(ValueError):tl.vals([T+1])
        self.assertTrue(all(r[0]<=T for r in tl.rows))

    def test_future_gap_closure_is_not_known_at_issue(self):
        tl=GuardedTimeline([(T-100,10,'a')],[(T-20,T+100)],'uni:Nessie Plushie',T)
        self.assertTrue(np.isnan(tl.vals([T])[0][0]))

    def test_original_curve_center_matches_native_and_earlier_same_plateau(self):
        rows=[]
        for t in range(T-10*DAY,T+1,3600):
            rows.extend([(t,0,'a'),(t+1800,100,'a'),(t+2400,0,'a')])
        rows=sorted(r for r in rows if r[0]<=T)
        tl=GuardedTimeline(rows,[],'uni:Nessie Plushie',T)
        ctx=SimpleNamespace(timelines={('uni','Nessie Plushie'):tl})
        for lags in ((1,),(1,2),(1,2,7)):
            native=TemplatePlanner(ctx,'uni','Nessie Plushie',lags=lags,minfit=.5).plan(T)
            p=FastTemplatePlanner(ctx,'uni','Nessie Plushie',lags=lags,minfit=.5)
            values=curve(p,T)
            self.assertEqual(plateau_choice(values,T),int(native[0]))
            self.assertLessEqual(plateau_choice(values,T,'quarter'),int(native[0]))
            self.assertLessEqual(plateau_choice(values,T,'left'),plateau_choice(values,T,'quarter'))

    def test_identified_gate_rejects_single_state_context(self):
        tl=GuardedTimeline([(T-10*DAY,0,'a'),(T-1,0,'a')],[],'uni:Nessie Plushie',T)
        plans,info=nessie_choices(tl,T)
        self.assertIsNone(plans['day127_identified_quarter'])
        self.assertIsNotNone(plans['day1_center'])

    def test_pattern_transfer_uses_own_country_flight(self):
        rows=[]
        for t in range(T-10*DAY,T+1,3600):rows.extend([(t,0,'a'),(t+1800,100,'a'),(t+2400,0,'a')])
        for key in ('can:Xanax','jap:Xanax'):
            tl=GuardedTimeline(rows,[],key,T)
            chosen,_=nessie_choices(tl,T,item_key=key)
            country,item=key.split(':',1)
            p=TemplatePlanner(SimpleNamespace(timelines={(country,item):tl}),country,item,lags=(1,),minfit=.5).plan(T)
            self.assertEqual(chosen['day1_center'],int(p[0]))
