"""Causal, leave-one-item-out stock-activity proxies, not purchase demand."""
import bisect
import math
from array import array
from collections import deque
from functools import lru_cache
from statistics import median

from research.true_zero_cycles import model


class SharedStockContext:
    def __init__(self,series,crosses):
        self.crosses=crosses
        self.series={}
        events=[]
        for key,rows in series.items():
            if not key.endswith(' Plushie'):
                continue
            times=array('q');quantities=array('q');sources=[]
            phases=model._ReplayPhases(crosses);past=deque(maxlen=64)
            for obs in rows:
                if (type(obs.epoch) is not int or type(obs.quantity) is not int
                    or obs.quantity<0 or not obs.source):
                    raise ValueError('invalid shared stock row')
                if times and obs.epoch<times[-1]:
                    raise ValueError('unordered shared stock rows')
                count=len(phases.high)
                phases.add(model.OBS(obs.epoch,200 if obs.quantity>0 else 0,obs.source))
                if len(phases.high)>count:
                    duration=phases.high[-1]
                    if len(past)>=3:
                        events.append((obs.epoch,key,math.log(duration/median(past))))
                    past.append(duration)
                times.append(obs.epoch);quantities.append(obs.quantity);sources.append(obs.source)
            self.series[key]=(times,quantities,tuple(sources))
        self.events=sorted(events)
        self.event_times=[r[0] for r in self.events]

    @classmethod
    def from_database(cls,db,roster,cutoff,crosses):
        series={}
        for key in sorted(roster):
            if not key.endswith(' Plushie'):
                continue
            country,name=key.split(':',1)
            raw=db.execute('SELECT timestamp,quantity,source FROM stock_history WHERE country=? AND lower(item_name)=lower(?) AND timestamp<=? ORDER BY timestamp,id LIMIT ?',
                           (country,name,cutoff,model.MAX_ITEM_CHANGE_ROWS+1)).fetchall()
            if len(raw)>model.MAX_ITEM_CHANGE_ROWS:
                raise ValueError('shared stock row cap exceeded')
            series[key]=[model.OBS(*row) for row in raw]
        return cls(series,crosses)

    @lru_cache(maxsize=8192)
    def at(self,asof,exclude_key):
        if self.crosses(asof,asof):
            return None
        quantities=[];drops=[]
        for key,(times,qs,sources) in self.series.items():
            if key==exclude_key:
                continue
            j=bisect.bisect_right(times,asof)-1
            if j<0 or asof-times[j]>86400:
                continue
            quantities.append(qs[j])
            i=bisect.bisect_right(times,asof-600)-1
            if (i>=0 and asof-600-times[i]<=86400 and qs[i]>0
                and not self.crosses(asof-600,asof)
                and len(set(sources[i:j+1]))==1
                and all(qs[k]<=qs[k-1] for k in range(i+1,j+1))):
                drops.append((qs[i]-qs[j])/qs[i])
        if len(quantities)<6:
            return None
        a=bisect.bisect_right(self.event_times,asof-7200)
        b=bisect.bisect_right(self.event_times,asof)
        ratios=[v for _,key,v in self.events[a:b] if key!=exclude_key]
        return (4*(sum(q>0 for q in quantities)/len(quantities)-.5),
                4*(sum(q>=30 for q in quantities)/len(quantities)-.5),
                4*sum(drops)/len(drops) if len(drops)>=3 else 0.,
                median(ratios) if len(ratios)>=6 else 0.)
