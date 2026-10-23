"""Incremental causal checkpoint4 cache for historical Monkey/Chamois replay.

Mirrors V47/V66 semantics in memory:
- eligible anchors every 30 minutes
- every anchor/expert outcome computed once, only after fully resolved
- 2d Monkey / 3d Chamois Beta(2,2) selector
- fast planner parity-preserving implementation
- no future evidence and no persistent writes
"""
from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

from research.v45_online_template_probe import EXPERTS, STRIDE, simulate_one
from research.v46_fast_template import FastTemplatePlanner
from research.v47_online_expert_cache import score_experts
from research.plushie_champions.common import (
    connect, load_gaps, Timeline, gap_overlap, TRAVEL_SECONDS,
    MAX_WAIT, GRACE, DAY,
)

TARGETS={
    "arg:Monkey Plushie":("arg","Monkey Plushie",2),
    "swi:Chamois Plushie":("swi","Chamois Plushie",3),
}


class IncrementalCheckpointSelector:
    def __init__(self,key):
        if key not in TARGETS:
            raise ValueError("unsupported checkpoint4 target")
        self.key=key
        self.country,self.item,self.days=TARGETS[key]
        self.entries={}
        self.last_anchor=None
        self.computed=0

    def _eligible(self,tl,gs,ge,now):
        maxfuture=MAX_WAIT+TRAVEL_SECONDS[self.country]+GRACE
        first=max(float(tl.ts[0])+8*DAY,now-self.days*DAY)
        lo=math.ceil(first/STRIDE)*STRIDE
        hi=math.floor((now-maxfuture)/STRIDE)*STRIDE
        if hi<lo:return []
        out=[]
        for s in range(lo,hi+1,STRIDE):
            a,_,_=tl.vals([s])
            if math.isnan(float(a[0])):continue
            if gap_overlap(gs,ge,s,s+maxfuture):continue
            out.append(s)
        return out

    def update_and_select(self,db,now):
        con=connect(db,readonly=True)
        try:
            gs,ge=load_gaps(con)
            tl=Timeline(con,gs,ge,self.country,self.item)
            anchors=self._eligible(tl,gs,ge,now)
            if not anchors:
                return {"status":"NO_FULLY_RESOLVED_ANCHORS"}
            wanted=set(anchors)
            # Drop entries that can no longer influence the 2d/3d selector.
            stale=[k for k in self.entries if k[0] not in wanted]
            for k in stale:self.entries.pop(k,None)

            missing_anchors=sorted({
                s for s in anchors
                if any((s,e) not in self.entries for e in range(len(EXPERTS)))
            })
            if missing_anchors:
                ctx=SimpleNamespace(timelines={(self.country,self.item):tl})
                planners={}
                for s in missing_anchors:
                    for e,(lags,look,shift) in enumerate(EXPERTS):
                        if (s,e) in self.entries:continue
                        if e not in planners:
                            planners[e]=FastTemplatePlanner(
                                ctx,self.country,self.item,lags=lags,
                                lookback=look,shift_range=shift)
                        outcome=simulate_one(
                            planners[e].plan,tl,s,TRAVEL_SECONDS[self.country])
                        self.entries[(s,e)]=(
                            outcome.get("success"),outcome.get("resolved_at"))
                        self.computed+=1

            selection=score_experts(
                self.entries,anchors,int(now),self.days,count=len(EXPERTS))
            if selection is None:
                return {"status":"SELECTOR_NOT_READY"}
            return {
                "status":"SELECTED",
                "expert_index":int(selection["expert_index"]),
                "posterior_score":float(selection["posterior_score"]),
                "resolved_count":int(selection["resolved_count"]),
                "anchors":len(anchors),
                "cached_decisions":len(self.entries),
                "computed_decisions_total":self.computed,
            }
        finally:
            con.close()
