"""Past-only daily phase analog, adapted from Nessie's archived template.

Uses raw indexed deltas, not hindsight bounce-cleaning or whole-dataset
feature normalization. This is a challenger, not a parity claim for the
archived champion. Returned support is uncalibrated template agreement.
"""
from __future__ import annotations
import bisect

DAY=86400
STEP=300
HORIZON=28800


class DailyTemplate:
    def __init__(self, observations, crosses):
        self.rows=observations
        self.times=[r.epoch for r in observations]
        self.crosses=crosses

    def state(self, clock, issued):
        if clock>issued:
            raise ValueError("template queried future stock")
        j=bisect.bisect_right(self.times,clock)-1
        if j<0 or clock-self.times[j]>86400 or self.crosses(self.times[j],clock):
            return None
        return self.rows[j].quantity>=30

    def plan(self, issued, flight):
        # Exact archived Nessie feature geometry: 2h lookback, one-day
        # lag, +/-1h shift, balanced phase fit >=0.5. Timing selection
        # variants are new; no winner is promoted into production.
        points=list(range(issued-7200,issued+1,STEP))
        current=[self.state(t,issued) for t in points]
        best=None
        for shift in range(-3600,3601,STEP):
            reference=[self.state(t-DAY-shift,issued) for t in points]
            pairs=[(a,b) for a,b in zip(current,reference) if a is not None and b is not None]
            if len(pairs)<6:
                continue
            balances=[]
            for phase in (False,True):
                values=[a==b for a,b in pairs if a==phase]
                if values:
                    balances.append(sum(values)/len(values))
            fit=sum(balances)/len(balances)
            raw=sum(a==b for a,b in pairs)/len(pairs)
            score=(fit,raw,-abs(shift),-shift)
            if best is None or score>best[0]:
                best=(score,shift)
        if best is None or best[0][0]<.5:
            return {"earliest":None,"center":None,"first_center":None,"status":"NO_MATCHING_DAILY_TEMPLATE"}
        shift=best[1]
        eligible=[]
        for delay in range(0,HORIZON+1,STEP):
            historical_arrival=issued+delay+flight-DAY-shift
            # All historical arrival evidence MUST resolve before issue.
            if historical_arrival+10>issued:
                continue
            a=bisect.bisect_right(self.times,historical_arrival)-1
            b=bisect.bisect_right(self.times,historical_arrival+10)-1
            if a<0 or b<0 or self.crosses(historical_arrival,historical_arrival+10):
                continue
            segment=self.rows[a:b+1]
            if len({r.source for r in segment})!=1:
                continue
            if all(r.quantity>=30 for r in segment) and self.state(historical_arrival+10,issued) is True:
                eligible.append(delay)
        groups=[]
        for delay in eligible:
            if not groups or delay-groups[-1][-1]>STEP:
                groups.append([delay])
            else:
                groups[-1].append(delay)
        # Immediate is eligible independently; future windows require
        # adjacent 5m support. Count narrow single bins as abstentions.
        credible=[g for g in groups if len(g)>=2 or g[0]==0]
        if not credible:
            return {"earliest":None,"center":None,"first_center":None,"status":"NO_SUSTAINED_TEMPLATE_WINDOW"}
        first=credible[0]
        widest=max(credible,key=lambda g:(len(g),-g[0]))
        return {"earliest":issued+first[0],"center":issued+widest[len(widest)//2],
                "first_center":issued if first[0]==0 else issued+first[len(first)//2],
                "fit":round(best[0][0],4),"shift_seconds":shift,
                "status":"UNCALIBRATED_DAILY_TEMPLATE_CANDIDATE"}
