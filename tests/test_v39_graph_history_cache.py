"""Bounded V39 history reuse is lossless at the requested rolling cutoff."""
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from web.history_cache_v39 import HistoryCache


class GraphHistoryCacheTests(unittest.TestCase):
    def setUp(self):
        self.cache=HistoryCache(max_entries=2)
        self.calls=0
        self.base=[
            {"timestamp":1000,"quantity":0,"cost":None,"source":"yata","anchor":True},
            {"timestamp":1200,"quantity":100,"cost":None,"source":"yata","anchor":False},
            {"timestamp":1500,"quantity":0,"cost":None,"source":"yata","anchor":False},
            {"timestamp":1800,"quantity":90,"cost":None,"source":"prometheus","anchor":False},
        ]
        self.rev=("uni","heather",1800,90,100,"yata",1,1800,6)

    def load(self,country,item,hours):
        self.calls+=1
        self.assertEqual((country,item,hours),("uni","Heather",168))
        return list(self.base)

    def test_cached_rolling_window_repositions_last_earlier_event(self):
        first=self.cache.get("uni","Heather",10,self.rev,self.load,now=1900)
        # A 10-minute lookback starts at 1300: prior quantity=100.
        self.assertEqual([(r["timestamp"],r["quantity"]) for r in first],
                         [(1300,100),(1500,0),(1800,90)])
        self.assertTrue(first[0]["anchor"])
        later=self.cache.get("uni","Heather",5,self.rev,self.load,now=2000)
        self.assertEqual([(r["timestamp"],r["quantity"]) for r in later],
                         [(1700,0),(1800,90)])
        self.assertEqual(self.calls,1)
        later[1]["quantity"]=-999
        again=self.cache.get("uni","Heather",5,self.rev,self.load,now=2000)
        self.assertEqual(again[1]["quantity"],90)

    def test_changed_source_revision_forces_reload(self):
        self.cache.get("uni","Heather",10,self.rev,self.load,now=1900)
        self.cache.get("uni","Heather",10,(*self.rev[:-1],7),self.load,now=1900)
        self.assertEqual(self.calls,2)

    def test_lru_entry_cap(self):
        items=["Heather","Wolverine Plushie","Nessie Plushie"]
        for item in items:
            self.cache.get("uni",item,10,self.rev,
                lambda *_: list(self.base),now=1900)
        self.assertEqual(len(self.cache._data),2)
        self.assertEqual(len(self.cache._item_locks),32)

    def test_concurrent_identical_requests_singleflight(self):
        lock=threading.Lock()
        def load(*args):
            with lock: self.calls+=1
            return list(self.base)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda _:self.cache.get(
                "uni","Heather",10,self.rev,load,now=1900),range(40)))
        self.assertEqual(self.calls,1)
        self.assertEqual(len(results),40)

    def test_absent_revision_rejected_without_loading(self):
        with self.assertRaises(ValueError):
            self.cache.get("uni","Heather",10,None,self.load,now=1900)
        self.assertEqual(self.calls,0)


if __name__=="__main__":
    unittest.main()
