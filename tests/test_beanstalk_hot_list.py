"""Read-only Beanstalk seven-item API, flight math, ranking and safety tests."""
import json
import subprocess
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web import beanstalk_hot_list as hot
from web.first_release_bridge import install_first_release

NOW = 1794615245
# Snapshot prices from the November 13 independent public 15-slot audit;
# synthetic FIXTURE only, never presented as live values.
PRICES = {
    "jap:Xanax": (649528, 841787),
    "can:Xanax": (774818, 841787),
    "sou:Xanax": (736427, 841787),
    "uni:Xanax": (781000, 841787),
    "chi:Panda Plushie": (400, 53870),
    "uae:Camel Plushie": (14000, 72396),
    "uni:Red Fox Plushie": (1000, 32991),
    "arg:Monkey Plushie": (400, 31678),
    "uni:Nessie Plushie": (200, 30397),
    "sou:Lion Plushie": (400, 54691),
    "chi:Peony": (5000, 54638),
    "uae:Tribulus Omanense": (6000, 63651),
    "sou:African Violet": (2000, 58461),
    "uni:Heather": (5000, 34711),
    "arg:Ceibo Flower": (500, 30898),
    "jap:Cherry Blossom": (500, 37688),
    "swi:Edelweiss": (900, 15402),
    "haw:Orchid": (700, 3754),
    "cay:Banana Orchid": (4000, 8374),
    "mex:Jaguar Plushie": (10000, 14220),
    "haw:Shark Fin": (20546, 65795),
    "chi:Pangolin Scales": (163000, 204254),
    "chi:Tiger Bone Powder": (29738, 69716),
    "jap:Whale Meat": (2125, 39811),
    "can:Bear Gall": (28803, 34924),
}


def catalog(prices=None):
    prices = PRICES if prices is None else prices
    countries = {}
    for key, (buy, market) in prices.items():
        country, name = key.split(":", 1)
        countries.setdefault(country, []).append({
            "item_name": name, "foreign_price": buy, "market_price": market,
            "market_price_stale": False,
        })
    return {"countries": [{"country": c, "items": items}
                          for c, items in countries.items()],
            "profitability": {"market_price_stale": False}}


def row(key, *, now=NOW, stale=False, no_departure=False):
    country = key.split(":")[0]
    seconds = hot.FLIGHTS_MINUTES[country] * 60
    return {"item_key": key,
            "valid_until_epoch": now-1 if stale else now+140,
            "source_heartbeat_epoch": now-220 if stale else now-20,
            "decision": {"status": "OK",
                         "player_flight_seconds": seconds,
                         "estimated_departure_epoch": None if no_departure else now+90,
                         "estimated_departure_deadline_epoch": now+125}}


class SevenPickTests(unittest.TestCase):
    def test_known_snapshot_returns_seven_curated_destinations_and_correct_hourly(self):
        board = {"status": "LIVE_BETA", "rows": [
            row("chi:Panda Plushie"),
            row("sou:African Violet", stale=True),
            row("uni:Heather"),
            row("jap:Xanax", no_departure=True),
        ]}
        result = hot.build_hot_list(catalog(), board, now=NOW)
        self.assertEqual(hot.SCHEMA, result["schema"])
        self.assertEqual("OK", result["status"])
        self.assertEqual(15, result["inventory_slots"])
        self.assertEqual("PI + pilot", result["flight_profile"])
        self.assertEqual("2026-11-14T", result["generated_at"][:11])  # 7:14 PM EST = next UTC day
        picks = result["picks"]
        self.assertEqual(7, len(picks))
        self.assertEqual(["xanax", "plushie", "plushie", "flower", "flower",
                          "nikeh", "nikeh"], [p["category"] for p in picks])
        self.assertEqual([
            "jap:Xanax",
            "chi:Panda Plushie", "uae:Camel Plushie",
            "sou:African Violet", "uni:Heather",
            "haw:Shark Fin", "jap:Whale Meat",
        ], [p["item_key"] for p in picks])
        self.assertGreaterEqual(len({p["country_code"] for p in picks}), 6)
        self.assertEqual(453532, picks[0]["estimated_round_trip_profit_per_hour"])
        self.assertEqual(229824, picks[5]["estimated_round_trip_profit_per_hour"])
        self.assertEqual(681810, picks[5]["estimated_profit_per_15_slots"])
        self.assertEqual("nikeh_npc", picks[5]["selling_method"])
        self.assertIsNone(picks[0]["recommended_departure_time"])
        self.assertIsNone(picks[3]["recommended_departure_time"])
        self.assertIsNone(picks[5]["recommended_departure_time"])
        self.assertEqual(NOW+90, picks[1]["recommended_departure_epoch"])
        self.assertTrue(picks[1]["recommended_departure_time"].endswith("Z"))
        self.assertNotIn("chi:Pangolin Scales", [p["item_key"] for p in picks])
        self.assertNotIn("swi:Edelweiss", [p["item_key"] for p in picks])

    def test_unverified_departure_is_null_without_changing_profitability(self):
        p = hot.build_hot_list(catalog(), {"status": "UNAVAILABLE", "rows": []}, now=NOW)
        self.assertEqual("OK", p["status"])
        self.assertTrue(all(v["recommended_departure_time"] is None for v in p["picks"]))
        self.assertTrue(all(v["departure_status"] == "UNVERIFIED" for v in p["picks"]))
        a = row("jap:Xanax", now=NOW)
        self.assertEqual(NOW+90, hot._departure(a, NOW))
        for broken in (
            row("jap:Xanax", now=NOW, stale=True),
            row("jap:Xanax", now=NOW, no_departure=True),
            {**a, "decision": {**a["decision"], "status": "STALE_DATA"}},
            {**a, "decision": {**a["decision"],
                              "estimated_departure_deadline_epoch": NOW-1}},
            {**a, "source_heartbeat_epoch": NOW+2},
        ):
            self.assertIsNone(hot._departure(broken, NOW))
        valid_now = {**a, "decision": {**a["decision"],
                                     "estimated_departure_epoch": NOW-20}}
        self.assertEqual(NOW, hot._departure(valid_now, NOW))

    def test_pangolin_only_allowed_when_the_highest_nikeh_hourly(self):
        prices = dict(PRICES)
        prices.pop("haw:Shark Fin")
        result = hot.build_hot_list(catalog(prices), {}, now=NOW)
        self.assertEqual("OK", result["status"])
        nikeh = [p["item_key"] for p in result["picks"] if p["category"]=="nikeh"]
        self.assertIn("chi:Pangolin Scales", nikeh)

    def test_stale_market_and_bad_country_mix_must_not_fabricate_results(self):
        c = catalog()
        c["profitability"]["market_price_stale"] = True
        with self.assertRaises(ValueError):
            hot.build_hot_list(c, {}, now=NOW)
        only = {"chi:Panda Plushie": PRICES["chi:Panda Plushie"],
                "jap:Xanax": PRICES["jap:Xanax"],
                "haw:Shark Fin": PRICES["haw:Shark Fin"]}
        result = hot.build_hot_list(catalog(only), {}, now=NOW)
        self.assertEqual("INSUFFICIENT_ELIGIBLE_ITEMS", result["status"])
        self.assertEqual([], result["picks"])

    def test_policy_stays_in_lockstep_with_torn_fren_browser_core(self):
        snippet = ("const c=require('./web/first_release_assets/hotlist-core.js');"
                   "console.log(JSON.stringify({flights:c.flights,candidates:[...c.HOT_CANDIDATES],"
                   "excluded:[...c.HOT_EXCLUSIONS],nikeh:c.NIKEH_PAYOUTS,floor:c.MIN_HOT_MARKET_VALUE}));")
        raw = subprocess.check_output(["node", "-e", snippet], text=True)
        js = json.loads(raw)
        self.assertEqual(hot.FLIGHTS_MINUTES,
                         {k: v[1] for k,v in js["flights"].items()})
        self.assertEqual(hot.CANDIDATES, set(js["candidates"]))
        self.assertEqual(hot.EXCLUSIONS, set(js["excluded"]))
        self.assertEqual(hot.NIKEH_PAYOUTS, js["nikeh"])
        self.assertEqual(hot.MARKET_FLOOR, js["floor"])


class EndpointTests(unittest.TestCase):
    def test_public_api_read_only_cors_and_unavailable_response(self):
        app = FastAPI()
        install_first_release(app)
        result = hot.build_hot_list(catalog(), {}, now=NOW)
        with TestClient(app) as client:
            with patch("web.beanstalk_hot_list.public_hot_list", return_value=result):
                resp = client.get("/api/beanstalk-hot-list")
                self.assertEqual(200, resp.status_code)
                self.assertEqual("*", resp.headers.get("access-control-allow-origin"))
                self.assertEqual(hot.SCHEMA, resp.json()["schema"])
                self.assertEqual(7, len(resp.json()["picks"]))
                self.assertIn("max-age=15", resp.headers.get("cache-control"))
            with patch("web.beanstalk_hot_list.public_hot_list",
                       return_value={**result, "status": "INSUFFICIENT_ELIGIBLE_ITEMS",
                                     "picks": []}):
                resp = client.get("/api/beanstalk-hot-list")
                self.assertEqual(503, resp.status_code)
                self.assertEqual([], resp.json()["picks"])


if __name__ == "__main__":
    unittest.main()
