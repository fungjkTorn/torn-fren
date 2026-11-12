"""V38 opt-in read-mostly catalog cache; zero scheduled tasks or DB writes.

Freshness is intentionally visible. Only one asynchronous rebuild is allowed.
Original /api/catalog behavior remains untouched unless explicitly enabled.
"""
from __future__ import annotations

import copy
import threading
import time
from concurrent.futures import ThreadPoolExecutor


class CatalogCache:
    def __init__(self, ttl=30, max_stale=180, *, clock=time.monotonic, executor=None):
        if not 1 <= ttl <= max_stale <= 600:
            raise ValueError("bad catalog cache freshness budget")
        self.ttl = ttl
        self.max_stale = max_stale
        self.clock = clock
        self.lock = threading.RLock()
        self.executor = executor or ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="v38-catalog"
        )
        self.value = None
        self.at = None
        self.future = None
        self.retry_after = 0

    def _finished(self, future):
        try:
            replacement = future.result()
            if not isinstance(replacement, dict) or "countries" not in replacement:
                raise ValueError("catalog builder returned invalid shape")
        except Exception:
            with self.lock:
                self.retry_after = self.clock() + 10
                if self.future is future:
                    self.future = None
            return
        with self.lock:
            if self.future is future:
                self.value = copy.deepcopy(replacement)
                self.at = self.clock()
                self.future = None
                self.retry_after = 0

    def get(self, builder):
        now = self.clock()
        with self.lock:
            if self.value is not None:
                age = max(0.0, now - self.at)
                if age >= self.ttl and self.future is None and now >= self.retry_after:
                    self.future = self.executor.submit(builder)
                    self.future.add_done_callback(self._finished)
                result = copy.deepcopy(self.value)
                result["catalog_cache"] = {
                    "status": ("fresh" if age < self.ttl else
                               "stale" if age <= self.max_stale else "overdue"),
                    "age_seconds": round(age, 3),
                    "ttl_seconds": self.ttl,
                    "revalidating": self.future is not None,
                }
                return result

        # Cold request preserves V37's successful synchronous build semantics.
        # Do not invent catalog rows or return a disguised placeholder.
        result = builder()
        if not isinstance(result, dict) or "countries" not in result:
            raise ValueError("catalog builder returned invalid shape")
        with self.lock:
            self.value = copy.deepcopy(result)
            self.at = self.clock()
        output = copy.deepcopy(result)
        output["catalog_cache"] = {
            "status": "fresh", "age_seconds": 0,
            "ttl_seconds": self.ttl, "revalidating": False,
        }
        return output
