"""Catalog read-hot cache tests; no network or live SQLite."""
import os
import unittest
from concurrent.futures import Future
from unittest.mock import patch

from web.catalog_cache_v38 import CatalogCache
from web.app import api_catalog


class ManualExecutor:
    def __init__(self):
        self.pending=[]

    def submit(self, fn):
        f=Future()
        self.pending.append((f, fn))
        return f

    def complete(self):
        future,fn=self.pending.pop(0)
        try:
            future.set_result(fn())
        except Exception as error:
            future.set_exception(error)


class CatalogCacheTests(unittest.TestCase):
    def setUp(self):
        self.t=[0.0]
        self.executor=ManualExecutor()
        self.cache=CatalogCache(ttl=30,max_stale=180,
                                clock=lambda:self.t[0],executor=self.executor)
        self.calls=[]
        def build():
            self.calls.append(self.t[0])
            return {"countries":[{"country":"uni","items":[{"quantity":len(self.calls)}]}],
                    "profitability":{"market_price_stale":False}}
        self.build=build

    def test_hot_reads_only_build_once_and_copy_safely(self):
        a=self.cache.get(self.build)
        a["countries"][0]["items"][0]["quantity"]=999
        for time in (2,10,29):
            self.t[0]=time
            b=self.cache.get(self.build)
            self.assertEqual(b["countries"][0]["items"][0]["quantity"],1)
            self.assertEqual(b["catalog_cache"]["status"],"fresh")
        self.assertEqual(len(self.calls),1)
        self.assertEqual(len(self.executor.pending),0)

    def test_one_nonblocking_refresh_serves_stale_explicitly(self):
        self.cache.get(self.build)
        self.t[0]=31
        stale=self.cache.get(self.build)
        self.assertEqual(stale["catalog_cache"]["status"],"stale")
        self.assertTrue(stale["catalog_cache"]["revalidating"])
        self.assertEqual(len(self.executor.pending),1)
        self.cache.get(self.build)
        self.assertEqual(len(self.executor.pending),1)
        self.executor.complete()
        fresh=self.cache.get(self.build)
        self.assertEqual(fresh["catalog_cache"]["status"],"fresh")
        self.assertEqual(fresh["countries"][0]["items"][0]["quantity"],2)

    def test_bad_refresh_is_not_relabelled_fresh(self):
        self.cache.get(self.build)
        self.t[0]=31
        def broken():
            raise RuntimeError("db unavailable")
        self.cache.get(broken)
        self.executor.complete()
        stale=self.cache.get(self.build)
        self.assertEqual(stale["catalog_cache"]["status"],"stale")
        self.assertEqual(len(self.executor.pending),0)
        self.t[0]=181
        overdue=self.cache.get(self.build)
        self.assertEqual(overdue["catalog_cache"]["status"],"overdue")
        self.assertTrue(overdue["catalog_cache"]["age_seconds"]>180)
        self.assertEqual(len(self.executor.pending),1)

    def test_disabled_flag_uses_original_catalog_builder(self):
        expected={"countries":[],"profitability":{}}
        with patch.dict(os.environ,{},clear=True):
            with patch("web.app._build_catalog_uncached",return_value=expected) as original:
                with patch("web.app._V38_CATALOG_CACHE") as cached:
                    self.assertEqual(api_catalog(),expected)
                    original.assert_called_once()
                    cached.get.assert_not_called()

    def test_explicit_flag_uses_cache(self):
        with patch.dict(os.environ,{"TORN_FREN_V38_CATALOG_CACHE":"1"}):
            with patch("web.app._build_catalog_uncached") as builder:
                with patch("web.app._V38_CATALOG_CACHE") as cache:
                    cache.get.return_value={"countries":[]}
                    self.assertEqual(api_catalog(),{"countries":[]})
                    cache.get.assert_called_once_with(builder)
                    builder.assert_not_called()


if __name__=="__main__":
    unittest.main()
