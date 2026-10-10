"""V46 CPU optimization of the exact original 24-bank TemplatePlanner.

Only vectorizes Timeline.vals probes; preserves the original balanced
shift-matching score, tie breaks, fit threshold, candidate grouping, and
feature output. Not scheduled until against-source parity tests pass.
"""
from __future__ import annotations

import numpy as np
from research.plushie_champions.common import (
    TemplatePlanner, STEP, MAX_WAIT, DAY,
)


class FastTemplatePlanner(TemplatePlanner):
    def _states(self, times):
        active,_,_=self.tl.vals(np.asarray(times,dtype=float))
        return active

    def _best_ref(self,q,lag_days):
        points=np.arange(q-self.lookback,q+1,STEP)
        cur=self._states(points)
        cur_ok=np.isfinite(cur)
        best=(-1.0,0,-1.0)
        for sh in range(-self.shift_range,self.shift_range+1,STEP):
            ref=self._states(points-lag_days*DAY-sh)
            mask=cur_ok & np.isfinite(ref)
            total=int(np.count_nonzero(mask))
            if total<6:
                continue
            a=cur[mask]
            b=ref[mask]
            eq=a==b
            vv=[]
            for v in (False,True):
                select=a==int(v)
                n=int(np.count_nonzero(select))
                if n:
                    vv.append(int(np.count_nonzero(eq[select]))/n)
            bal=sum(vv)/len(vv) if vv else -1
            raw=int(np.count_nonzero(eq))/total
            if (bal>best[0] or
                (bal==best[0] and raw>best[2]) or
                (bal==best[0] and raw==best[2] and abs(sh)<abs(best[1]))):
                best=(bal,sh,raw)
        return best

    def plan(self,q):
        key=int(q)
        if key in self.cache:
            return self.cache[key]
        refs=[]
        for d in self.lags:
            fit,sh,raw=self._best_ref(q,d)
            if fit>=self.minfit:
                refs.append((d,sh,fit,raw))
        delays=np.arange(0,MAX_WAIT+1,STEP)
        arrival=q+self.travel+delays
        numerator=np.zeros(len(delays),dtype=float)
        denominator=np.zeros(len(delays),dtype=float)
        for d,sh,fit,raw in refs:
            state=self._states(arrival-d*DAY-sh)
            good=np.isfinite(state)
            w=fit*fit/d
            numerator[good]+=w*state[good]
            denominator[good]+=w
        vals=[(int(delay),float(numerator[j]/denominator[j]))
              for j,delay in enumerate(delays) if denominator[j]]
        if vals:
            bestp=max(v for _,v in vals)
            cand=[x for x in vals if x[1]>=bestp-.04]
            groups=[]
            for x in cand:
                if not groups or x[0]-groups[-1][-1][0]>STEP:
                    groups.append([x])
                else:
                    groups[-1].append(x)
            g=max(groups,key=lambda z:(sum(v for _,v in z)/len(z),len(z),-z[0][0]))
            delay,prob=g[len(g)//2]
        else:
            delay,prob=0,.5
        feat={'fit':sum(x[2] for x in refs)/len(refs) if refs else 0.0,
              'maxfit':max((x[2] for x in refs),default=0.0),
              'raw':sum(x[3] for x in refs)/len(refs) if refs else 0.0,
              'refs':len(refs),
              'shift':sum(abs(x[1]) for x in refs)/len(refs)/max(self.shift_range,1) if refs else 0.0,
              'prob':prob,'delay':delay}
        self.cache[key]=(q+delay,float(prob),feat)
        return self.cache[key]
