"""V93 no-poll observer design: freshness and dedup are explicit."""
import unittest
from research import v93_arrival_observation_policy as o

NOW=1791650000


def snap(update=NOW-20,source="yata",qty=85):
    return {
        "source":source,"timestamp":NOW-10,
        "stocks":{"jap":{"update":update,
                          "stocks":[{"name":"Xanax","quantity":qty,"id":3}]}}
    }


def target(fid,at,item="jap:Xanax"):
    return o.ArrivalTarget(
        forecast_id=fid,item_key=item,
        arrival_epoch=at,forecast_issued_epoch=NOW-20,
        valid_until_epoch=NOW+280)


class ObserverDesignTests(unittest.TestCase):
    def test_country_update_timestamp_is_not_fetch_timestamp(self):
        d=o.decode_export_observation(snap(),item_key="jap:Xanax",
                                      received_epoch=NOW)
        self.assertEqual(d["status"],"FRESH_PROVIDER_OBSERVATION")
        self.assertEqual(d["quantity"],85)
        self.assertEqual(d["country_update_epoch"],NOW-20)
        self.assertEqual(d["country_age_seconds"],20)

    def test_stale_yata_even_if_fetched_now(self):
        d=o.decode_export_observation(snap(update=NOW-180),
                                      item_key="jap:Xanax",
                                      received_epoch=NOW)
        self.assertEqual(d["status"],"COUNTRY_UPDATE_STALE")
        self.assertEqual(d["quantity"],85)
        self.assertNotEqual(d["export_timestamp"],d["country_update_epoch"])

    def test_bad_or_missing_provider_update_is_unscorable(self):
        for t,expected in (
            (None,"COUNTRY_TIMESTAMP_MISSING"),
            (NOW+20,"COUNTRY_TIMESTAMP_IN_FUTURE"),
            ("", "COUNTRY_TIMESTAMP_MISSING"),
        ):
            r=o.decode_export_observation(snap(update=t),item_key="jap:Xanax",
                                          received_epoch=NOW)
            self.assertEqual(r["status"],expected)

    def test_stock_missing_or_duplicate_invalid(self):
        absent=o.decode_export_observation(snap(),item_key="jap:Other",
                                           received_epoch=NOW)
        self.assertEqual(absent["status"],"ITEM_MISSING_OR_DUPLICATED")
        duplicate=snap()
        duplicate["stocks"]["jap"]["stocks"].append(
            {"name":"Xanax","quantity":90})
        r=o.decode_export_observation(duplicate,item_key="jap:Xanax",
                                      received_epoch=NOW)
        self.assertEqual(r["status"],"ITEM_MISSING_OR_DUPLICATED")

    def test_zero_stock_is_valid_fresh_miss_observation(self):
        d=o.decode_export_observation(snap(qty=0),item_key="jap:Xanax",
                                      received_epoch=NOW)
        self.assertEqual(d["status"],"FRESH_PROVIDER_OBSERVATION")
        self.assertEqual(d["quantity"],0)

    def test_zero_extra_requests_without_explicit_budget(self):
        result=o.plan_extra_observations(
            [target("a",NOW+120),target("b",NOW+124)],now=NOW)
        self.assertEqual(result["unique_item_arrival_targets"],2)
        self.assertEqual(result["coalesced_precise_windows"],1)
        self.assertEqual(result["hypothetical_extra_fetches"],0)
        self.assertEqual(result["skipped_window_counts"]["DISABLED_BY_DEFAULT"],1)

    def test_precise_windows_overlap_and_deduplicate_same_item(self):
        results=o.plan_extra_observations(
            [target("first",NOW+100),
             target("repeated",NOW+100),
             target("other_item",NOW+107,"chi:Panda Plushie"),
             target("after_window",NOW+116)],
            now=NOW,per_hour_budget=5,min_request_spacing=1)
        self.assertEqual(results["unique_item_arrival_targets"],3)
        self.assertEqual(results["coalesced_precise_windows"],2)
        self.assertEqual(results["hypothetical_extra_fetches"],2)
        first=results["hypothetical_plan"][0]
        self.assertEqual(first["planned_request_epoch"],NOW+107)
        self.assertEqual(first["item_keys"],["chi:Panda Plushie","jap:Xanax"])
        self.assertEqual(len(first["forecast_ids"]),2)

    def test_budget_and_rate_limit_apply_globally(self):
        a=[target(str(i),NOW+100+i*20) for i in range(20)]
        r=o.plan_extra_observations(a,now=NOW,
            per_hour_budget=3,min_request_spacing=60)
        self.assertLessEqual(r["hypothetical_extra_fetches"],3)
        self.assertGreater(r["skipped_window_counts"].get("RATE_LIMIT_SPACING",0),0)

    def test_invalid_expired_no_forecast_and_future_out_of_range(self):
        malformed=[
            target("bad",NOW+30000),
            o.ArrivalTarget("", "jap:Xanax", NOW+200,NOW-20,NOW+280),
            o.ArrivalTarget("x", "jap:Xanax", NOW+200,NOW-20,NOW-1),
            {"country":"jap"},
        ]
        result=o.plan_extra_observations(malformed,now=NOW,per_hour_budget=3)
        self.assertEqual(result["hypothetical_extra_fetches"],0)
        self.assertEqual(sum(result["excluded_target_counts"].values()),4)

    def test_pure_deterministic_no_source_mutations(self):
        initial=[target("a",NOW+100),target("b",NOW+103)]
        before=list(initial)
        one=o.plan_extra_observations(initial,now=NOW,per_hour_budget=2)
        two=o.plan_extra_observations(initial,now=NOW,per_hour_budget=2)
        self.assertEqual(one,two)
        self.assertEqual(initial,before)


if __name__=="__main__":
    unittest.main()
