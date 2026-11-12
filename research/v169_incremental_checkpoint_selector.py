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


class _ResolvedPlanner(FastTemplatePlanner):
    """Memoize identical lag/shift fits shared by the original expert bank."""
    def __init__(self,*args,reference_cache,**kwargs):
        super().__init__(*args,**kwargs);self.reference_cache=reference_cache
    def _best_ref(self,q,lag_days):
        key=(float(q),lag_days,self.lookback,self.shift_range)
        if key not in self.reference_cache:
            self.reference_cache[key]=super()._best_ref(q,lag_days)
        return self.reference_cache[key]


class IncrementalCheckpointSelector:
    def __init__(self,key,*,min_qty=30,grace=GRACE,reuse_resolved_plans=False,policy_consistent_labels=False):
        if policy_consistent_labels and (min_qty!=31 or grace!=0):raise ValueError('V5 labels require target31 and zero grace')
        self.policy_consistent_labels=policy_consistent_labels
        self.reuse_resolved_plans=reuse_resolved_plans
        self.plan_caches={};self.reference_cache={};self.cache_source=None;self.cache_prefix=None;self.cache_gaps=None;self.cache_cutoff=None
        self.min_qty=min_qty;self.grace=grace
        if key not in TARGETS:
            raise ValueError("unsupported checkpoint4 target")
        self.key=key
        self.country,self.item,self.days=TARGETS[key]
        self.entries={}
        self.last_anchor=None
        self.computed=0

    def _eligible(self,tl,gs,ge,now):
        maxfuture=MAX_WAIT+TRAVEL_SECONDS[self.country]+self.grace+(180 if self.policy_consistent_labels else 0)
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
            tl=Timeline(con,gs,ge,self.country,self.item,min_qty=self.min_qty)
            if self.reuse_resolved_plans:
                source=str(Path(db).resolve())
                # Only a sealed append-only causal mirror may reuse these fits.
                # Protect the history every cached plan could query. A training
                # plan's q is at least flight seconds before the old issue.
                if source!=self.cache_source:
                    self.plan_caches.clear();self.reference_cache.clear();self.cache_prefix=None
                if self.cache_prefix is not None:
                    prefix=tuple(r for r in tl.rows if r[0]<=self.cache_cutoff)
                    gap_prefix=tuple((float(a),min(float(b),self.cache_cutoff)) for a,b in zip(gs,ge) if a<=self.cache_cutoff)
                    if prefix!=self.cache_prefix or gap_prefix!=self.cache_gaps:
                        raise ValueError('sealed causal prefix changed; resolved plan reuse rejected')
                self.cache_source=source;self.cache_cutoff=now-600
                self.cache_prefix=tuple(r for r in tl.rows if r[0]<=self.cache_cutoff)
                self.cache_gaps=tuple((float(a),min(float(b),self.cache_cutoff)) for a,b in zip(gs,ge) if a<=self.cache_cutoff)
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
                label_at_arrival=None
                if self.policy_consistent_labels:
                    from functools import lru_cache
                    from services.simulated_trip_evidence import grade_trip
                    label_rows=con.execute('SELECT timestamp,quantity,source FROM stock_history WHERE country=? AND lower(item_name)=lower(?) AND timestamp<=? ORDER BY timestamp,id',(self.country,self.item,now)).fetchall()
                    label_polls=[r[0] for r in con.execute("SELECT timestamp FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1 AND timestamp<=? ORDER BY timestamp",(now,))]
                    label_gaps=con.execute('SELECT start_timestamp,end_timestamp FROM collection_gaps WHERE start_timestamp<=?',(now,)).fetchall()
                    has_receipts=con.execute("SELECT 1 FROM sqlite_master WHERE name='country_stock_observations'").fetchone()
                    label_receipts=con.execute('SELECT received_epoch,country_update_epoch,clock_status,source FROM country_stock_observations WHERE country=? AND received_epoch<=? ORDER BY received_epoch,id',(self.country,now)).fetchall() if has_receipts else []
                    @lru_cache(maxsize=10000)
                    def label_at_arrival(arrival):
                        status=grade_trip(arrival,label_rows,label_polls,label_gaps,now,label_receipts)['status']
                        return 1 if status=='SUCCESS' else 0 if status=='FAILURE' else None
                ctx=SimpleNamespace(timelines={(self.country,self.item):tl})
                planners={}
                for s in missing_anchors:
                    for e,(lags,look,shift) in enumerate(EXPERTS):
                        if (s,e) in self.entries:continue
                        if e not in planners:
                            if self.reuse_resolved_plans:
                                planners[e]=_ResolvedPlanner(ctx,self.country,self.item,lags=lags,
                                    lookback=look,shift_range=shift,reference_cache=self.reference_cache)
                                planners[e].cache=self.plan_caches.setdefault(e,{})
                            else:
                                planners[e]=FastTemplatePlanner(
                                    ctx,self.country,self.item,lags=lags,
                                    lookback=look,shift_range=shift)
                        outcome=simulate_one(
                            planners[e].plan,tl,s,TRAVEL_SECONDS[self.country],grace=self.grace,label_at_arrival=label_at_arrival)
                        self.entries[(s,e)]=(
                            outcome.get("success"),outcome.get("resolved_at"))
                        self.computed+=1

            if self.reuse_resolved_plans and anchors:
                oldest=min(anchors)
                for cache in self.plan_caches.values():
                    for q in [q for q in cache if q<oldest]:cache.pop(q)
                for key in [key for key in self.reference_cache if key[0]<oldest]:self.reference_cache.pop(key)
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
                "arrival_stock_threshold":self.min_qty,"arrival_grace_seconds":self.grace,
                "resolved_label_policy":"V5_STOCK_AT_ARRIVAL" if self.policy_consistent_labels else "LEGACY_COMPLETED_WINDOWS",
            }
        finally:
            con.close()
