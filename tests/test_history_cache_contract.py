"""Source-revision cache contract; no database or network required."""
import unittest
from web.history_cache_v39 import HistoryCache


class HistoryCacheTests(unittest.TestCase):
    def test_revision_reuse_and_invalidation(self):
        cache = HistoryCache(max_entries=2)
        calls = []
        def load(country, item, minutes):
            calls.append((country, item, minutes))
            return [{"timestamp": 900, "quantity": 40},
                    {"timestamp": 990, "quantity": 30}]
        first = cache.get("arg", "Monkey Plushie", 2, (1,), load, now=1000)
        second = cache.get("arg", "Monkey Plushie", 2, (1,), load, now=1000)
        self.assertEqual(first, second)
        self.assertEqual(len(calls), 1)
        cache.get("arg", "Monkey Plushie", 2, (2,), load, now=1000)
        self.assertEqual(len(calls), 2)

    def test_anchoring_and_immutable_cached_rows(self):
        cache = HistoryCache()
        def load(*_):
            return [{"timestamp": 100, "quantity": 50},
                    {"timestamp": 195, "quantity": 30}]
        rows = cache.get("arg", "Monkey Plushie", 1, ("r",), load, now=200)
        self.assertEqual(rows[0]["timestamp"], 140)
        self.assertTrue(rows[0]["anchor"])
        rows[-1]["quantity"] = 0
        again = cache.get("arg", "Monkey Plushie", 1, ("r",), load, now=200)
        self.assertEqual(again[-1]["quantity"], 30)

    def test_requires_revision(self):
        cache = HistoryCache()
        with self.assertRaises(ValueError):
            cache.get("arg", "Monkey Plushie", 1, None, lambda *args: [], now=200)


if __name__ == "__main__":
    unittest.main()
