"""Per-item, source-revision, bounded seven-day stock graph cache.

The DB history helper is expensive (full history provider-bounce cleanup).
Compute it once per source/gap/5-minute revision; re-window existing event
rows cheaply for every graph request. Cache holds no SQLite connections.
Only used under explicit V39 website cache feature flag.
"""
from __future__ import annotations

from collections import OrderedDict
import copy
import threading
import time


class HistoryCache:
    def __init__(self,*,max_entries=64):
        if not 1<=max_entries<=256:
            raise ValueError("invalid entry bound")
        self.max_entries=int(max_entries)
        self._data=OrderedDict()
        self._lock=threading.RLock()
        self._item_locks=[threading.Lock() for _ in range(32)]

    def _slice(self,base,*,minutes,now):
        cutoff=int(now)-int(minutes)*60
        previous=None
        visible=[]
        for row in base:
            ts=int(row["timestamp"])
            if ts<cutoff:
                previous=row
            elif ts<=now:
                visible.append(copy.deepcopy(row))
        output=[]
        if previous is not None:
            output.append({
                "timestamp":cutoff,"quantity":previous["quantity"],
                "cost":None,"source":previous.get("source"),"anchor":True,
            })
        for row in visible:
            if row.get("anchor"):
                # Existing seven-day boundary: shift synthetic anchor to the
                # requested window; it is not a true observed quantity event.
                row["timestamp"]=cutoff
            output.append(row)
        return output

    def get(self,country,item,minutes,revision,loader,*,now=None):
        now=time.time() if now is None else float(now)
        key=(country.lower(),item.lower())
        if not isinstance(revision,tuple) or not revision:
            raise ValueError("cache needs a verified immutable source revision")
        with self._lock:
            cached=self._data.get(key)
            if cached and cached["revision"]==revision:
                self._data.move_to_end(key)
                return self._slice(cached["base"],minutes=minutes,now=now)
            item_lock=self._item_locks[hash(key)%len(self._item_locks)]
        # Different items can rebuild concurrently; identical requests share
        # one cold rebuild per item.
        with item_lock:
            with self._lock:
                cached=self._data.get(key)
                if cached and cached["revision"]==revision:
                    self._data.move_to_end(key)
                    return self._slice(cached["base"],minutes=minutes,now=now)
            base=loader(country,item,168)
            if not isinstance(base,list):
                raise ValueError("invalid stock history response")
            with self._lock:
                self._data[key]={"revision":revision,
                                 "base":copy.deepcopy(base)}
                self._data.move_to_end(key)
                while len(self._data)>self.max_entries:
                    self._data.popitem(last=False)
                result=self._slice(base,minutes=minutes,now=now)
            return result
