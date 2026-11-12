"""Proof that V46 vectorized template scoring matches source winner."""
import unittest
from types import SimpleNamespace

import numpy as np

from research.plushie_champions.common import TemplatePlanner, DAY, STEP
from research.v46_fast_template import FastTemplatePlanner


class StockTimeline:
    """Step observations with missing source coverage and target ref days."""
    def __init__(self):
        rng=np.random.default_rng(20261010)
        self.times=np.arange(0,17*DAY+STEP,600,dtype=float)
        # Predictable regime switch + quantity noise, only >=30 matters.
        cycle=(self.times//2700).astype(int)
        live=((cycle%7)<=2) ^ ((self.times//DAY).astype(int)%5==4)
        noise=rng.integers(0,7,len(self.times))
        self.q=np.where(live,60+noise,noise).astype(float)

    def vals(self,t):
        t=np.asarray(t,float)
        idx=np.searchsorted(self.times,t,"right")-1
        valid=idx>=0
        safe=np.maximum(idx,0)
        q=self.q[safe].copy()
        q[~valid]=np.nan
        # Gap in the middle: neither implementation may bridge it.
        gap=(t>=8.5*DAY)&(t<8.7*DAY)
        q[gap]=np.nan
        active=np.where(np.isfinite(q),np.where(q>=30,1.0,0.0),np.nan)
        age=np.where(np.isfinite(q),t-self.times[safe],np.nan)
        return active,q,age


class FastTemplateParityTests(unittest.TestCase):
    def setUp(self):
        self.ctx=SimpleNamespace(timelines={
            ("arg","Monkey Plushie"):StockTimeline()
        })

    def planner(self,klass,**kwargs):
        return klass(self.ctx,"arg","Monkey Plushie",**kwargs)

    def test_original_winner_expert_bank_is_exact_at_selected_queries(self):
        queries=[12*DAY+3600,12*DAY+4500,12*DAY+5100]
        configs=[
            {"lags":(1,),"lookback":7200,"shift_range":3600},
            {"lags":(2,),"lookback":14400,"shift_range":7200},
            {"lags":(7,),"lookback":7200,"shift_range":3600},
            {"lags":(1,2,7),"lookback":14400,"shift_range":3600},
            {"lags":(1,7),"lookback":7200,"shift_range":7200},
        ]
        for config in configs:
            a=self.planner(TemplatePlanner,**config)
            b=self.planner(FastTemplatePlanner,**config)
            for q in queries:
                with self.subTest(config=config,q=q):
                    self.assertEqual(a.plan(q),b.plan(q))
                    self.assertEqual(a.plan(q),b.plan(q))

    def test_gap_and_insufficient_reference_state(self):
        for q in [8.6*DAY,DAY,2*DAY,16*DAY+2400]:
            config={"lags":(1,2,7),"lookback":7200,
                    "shift_range":1200,"minfit":.48}
            slow=self.planner(TemplatePlanner,**config)
            fast=self.planner(FastTemplatePlanner,**config)
            with self.subTest(q=q):
                self.assertEqual(slow.plan(q),fast.plan(q))

    def test_standalone_shift_fits_identical(self):
        a=self.planner(TemplatePlanner,lags=(1,2,7),
                       lookback=14400,shift_range=1800)
        b=self.planner(FastTemplatePlanner,lags=(1,2,7),
                       lookback=14400,shift_range=1800)
        for day in (1,2,7):
            for q in (12*DAY+7200,14*DAY+3600):
                self.assertEqual(a._best_ref(q,day),b._best_ref(q,day))


if __name__=="__main__":
    unittest.main()
