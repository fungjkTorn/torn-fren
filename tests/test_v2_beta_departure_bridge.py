"""First reachable V2 restock-cycle flight selection; synthetic deterministic QA."""
import copy
import unittest

from research.v2_beta_departure_bridge import build_item_timeline
from research.plushie_champions.common import TRAVEL_SECONDS

NOW = 1791800000

def cycle(n, *, country="can", restock=3000, upper=3250, target=3300,
          depleted=4200, lifetime=1200, model="original-v2"):
    return {
        "prediction_number": n,
        "estimate_timestamp": NOW + restock,
        "window_start_timestamp": NOW + restock-200,
        "window_end_timestamp": NOW + upper,
        "recommended_arrival_timestamp": NOW + target,
        "target_depletion_timestamp": NOW + depleted,
        "expected_stock_lifetime_seconds": lifetime,
        "travel_seconds": TRAVEL_SECONDS[country],
        "model_name": model,
        "travel_reliability": "marginal",
    }

def run(chain, *, country="can", item="Crocus", now=NOW, issue=NOW-20,
        source=NOW-40, valid=None, incumbent=None, stale=False):
    return build_item_timeline(
        country+":"+item, {"predictions": chain},now=now,
        issued_at=issue,stock_as_of=source,valid_until=valid,
        incumbent=incumbent,forecast_stale=stale)

def incumbent(country="can", *, dep=NOW+200, stock=NOW-10):
    return {
        "item_key":country+":Crocus","model_family":"V18",
        "model_config":"dyn5","status":"RESEARCH_PROPOSAL_ONLY",
        "computed_at":NOW-20,"stock_as_of":stock,
        "valid_until":NOW+280,"departure":dep,
        "arrival":dep+TRAVEL_SECONDS[country],
        "actionable":True,"prediction_accuracy_verified":False,
    }

class FirstReachableDepartureTests(unittest.TestCase):
    def test_skip_unreachable_p1_pick_next_restock_cycle(self):
        short=cycle(1,restock=600,upper=660,target=750,depleted=900,lifetime=300)
        second=cycle(2)
        original=copy.deepcopy([short,second])
        result=run([short,second])
        first=result["first_reachable"]
        self.assertEqual(first["prediction_number"],2)
        self.assertEqual(first["earliest_departure_epoch"],NOW+1680)
        self.assertEqual(first["arrival_epoch"],NOW+3300)
        self.assertEqual(first["status"],"FUTURE_WATCH_RECONFIRM_REQUIRED")
        self.assertEqual(result["next_predicted_restock"]["cycle"],1)
        self.assertEqual(result["skipped_by_reason"],{"DEPARTURE_WINDOW_EXPIRED":1})
        self.assertIsNone(first["estimated_stock_at_arrival_30_or_more"])
        self.assertEqual([short,second],original)

    def test_when_window_already_open_leave_now_is_first_eligible(self):
        p=cycle(1,restock=1000,upper=1150,target=1500,
                depleted=2500,lifetime=1200)
        r=run([p])
        self.assertEqual(r["first_reachable"]["earliest_departure_epoch"],NOW)
        self.assertEqual(r["first_reachable"]["status"],"PROVISIONAL_LEAVE_NOW")
        self.assertEqual(r["first_reachable"]["arrival_epoch"],
                         NOW+TRAVEL_SECONDS["can"])
        self.assertFalse(r["stock_at_arrival_at_least_30_verified"])

    def test_conservative_depletion_excludes_false_zero_width_go(self):
        p=cycle(1,depleted=3300,lifetime=1200)
        r=run([p])
        self.assertEqual(r["status"],"NO_REACHABLE_V2_WINDOW")
        self.assertIn("NO_FEASIBLE_STOCKED_INTERVAL",r["skipped_by_reason"])

    def test_country_specific_uk_long_flight_and_second_cycle(self):
        first=cycle(1,country="uni",restock=600,
                    upper=750,target=900,depleted=1300,lifetime=600)
        second=cycle(2,country="uni",restock=10000,
                     upper=10400,target=10500,depleted=11500,lifetime=1200)
        r=run([first,second],country="uni",item="Nessie Plushie")
        self.assertEqual(r["first_reachable"]["prediction_number"],2)
        self.assertEqual(r["first_reachable"]["earliest_departure_epoch"],NOW+4140)
        self.assertEqual(r["first_reachable"]["arrival_epoch"],NOW+10500)

    def test_short_restock_cadence_flags_unreasonably_long_modeled_wait(self):
        # A 30-minute observed restock cadence is incompatible with an
        # unexplained 2-hour gap between projected cycles. Preserve the
        # first reachable modeled cycle, but label the long wait untrusted.
        p1=cycle(1,restock=500,upper=600,target=650,
                 depleted=750,lifetime=300)
        p2=cycle(2,restock=10000,upper=10300,target=10400,
                 depleted=11500,lifetime=1100)
        r=build_item_timeline("can:Crocus",{"predictions":[p1,p2]},
                              now=NOW,issued_at=NOW-20,stock_as_of=NOW-30,
                              observed_median_restock_cadence_seconds=1800)
        self.assertEqual(r["first_reachable"]["prediction_number"],2)
        self.assertEqual(r["first_reachable"]["status"],
                         "LONG_WAIT_VERIFY_NEARER_RESTOCKS")
        self.assertIn("MODELED_RESTOCK_GAP_EXCEEDS_OBSERVED_CADENCE",
                      r["cadence_alerts"])
        self.assertIn("LONG_WAIT_MULTIPLE_OBSERVED_RESTOCK_PERIODS",
                      r["cadence_alerts"])
        self.assertFalse(r["stock_at_arrival_at_least_30_verified"])

    def test_reasonable_wait_under_cadence_is_not_suppressed(self):
        p=cycle(1)
        r=build_item_timeline("can:Crocus",{"predictions":[p]},
                              now=NOW,issued_at=NOW-20,stock_as_of=NOW-30,
                              observed_median_restock_cadence_seconds=1800)
        self.assertEqual(r["first_reachable"]["earliest_departure_epoch"],
                         NOW+1680)
        self.assertEqual(r["cadence_alerts"],[])
        self.assertEqual(r["first_reachable"]["status"],
                         "FUTURE_WATCH_RECONFIRM_REQUIRED")

    def test_no_unsupported_assumption_if_cadence_unknown(self):
        p1=cycle(1,restock=500,upper=600,target=650,
                 depleted=750,lifetime=300)
        p2=cycle(2,restock=10000,upper=10300,target=10400,
                 depleted=11500,lifetime=1100)
        r=run([p1,p2])
        self.assertEqual(r["cadence_alerts"],[])
        self.assertEqual(r["first_reachable"]["status"],
                         "FUTURE_WATCH_RECONFIRM_REQUIRED")

    def test_fake_or_unrealistic_cadence_is_rejected(self):
        with self.assertRaises(ValueError):
            build_item_timeline("can:Crocus",{"predictions":[cycle(1)]},
                                now=NOW,issued_at=NOW-20,stock_as_of=NOW-30,
                                observed_median_restock_cadence_seconds=0)

    def test_expired_issuance_not_rescued_by_fresh_http_response(self):
        r=run([cycle(1)],issue=NOW-301,source=NOW-330)
        self.assertEqual(r["status"],"MODEL_ISSUE_EXPIRED")
        self.assertIsNone(r["first_reachable"])

    def test_explicit_model_expiry_takes_precedence(self):
        r=run([cycle(1)],valid=NOW-1)
        self.assertEqual(r["status"],"MODEL_ISSUE_EXPIRED")
        self.assertEqual(r["refresh_in_seconds"],0)

    def test_source_stale_and_no_issuance_withdraw_v2(self):
        r=run([cycle(1)],source=NOW-190)
        self.assertEqual(r["status"],"COLLECTOR_EVIDENCE_STALE")
        self.assertIsNone(r["first_reachable"])
        unknown=run([cycle(1)],issue=None)
        self.assertEqual(unknown["status"],"ISSUANCE_OR_SOURCE_UNKNOWN")
        self.assertIsNone(unknown["first_reachable"])

    def test_specialist_arrival_does_not_replace_v2_restock(self):
        r=run([cycle(1)],incumbent=incumbent())
        self.assertEqual(r["first_reachable"]["forecast_type"],
                         "V2_RESTOCK_AND_STOCK_LIFETIME")
        self.assertEqual(r["incumbent_specialist"]["model_family"],"V18")
        self.assertEqual(r["incumbent_specialist"]["departure_epoch"],NOW+200)
        self.assertEqual(r["incumbent_specialist"]["status"],"DEPART_SOON_PROVISIONAL")
        self.assertFalse(r["incumbent_specialist"]["verified_stock_at_arrival"])
        self.assertTrue(r["specialist_does_not_replace_v2_restock"])

    def test_specialist_flight_mismatch_not_presented(self):
        p=incumbent()
        p["arrival"]=p["departure"]+TRAVEL_SECONDS["uni"]
        r=run([cycle(1)],incumbent=p)
        self.assertEqual(r["incumbent_specialist"]["status"],
                         "SPECIALIST_FLIGHT_OR_HORIZON_INVALID")
        self.assertIsNone(r["incumbent_specialist"]["departure_epoch"])

    def test_specialist_and_graph_fail_separately(self):
        r=run([cycle(1)],incumbent=incumbent(),stale=True)
        self.assertEqual(r["status"],"V2_WARMING_OR_STALE")
        self.assertIsNone(r["first_reachable"])
        self.assertEqual(r["incumbent_specialist"]["model_family"],"V18")

    def test_eight_hour_issued_horizon_is_distinct_from_v2_twelve_hour_graph(self):
        late=cycle(1,restock=35000,upper=35500,
                   target=35600,depleted=37000,lifetime=1200)
        r=run([late])
        self.assertEqual(r["status"],"NO_REACHABLE_V2_WINDOW")
        self.assertEqual(r["skipped_by_reason"],
                         {"BEYOND_EIGHT_HOUR_ISSUE_HORIZON":1})
        self.assertIsNotNone(r["next_predicted_restock"])

    def test_travel_mismatch_and_duplicate_cycle_fail_closed(self):
        p=cycle(1)
        bad={**p,"travel_seconds":999}
        r=run([bad])
        self.assertEqual(r["status"],"TRAVEL_TIME_MISMATCH")
        self.assertEqual(r["cycle_candidates"],[])
        r2=run([p,p])
        self.assertEqual(r2["status"],"INVALID_V2_CYCLE_IDENTITIES")

    def test_other_item_specialist_cannot_be_attached_to_crocus(self):
        mismatch=incumbent()
        mismatch["item_key"]="can:Wolverine Plushie"
        r=run([cycle(1)],incumbent=mismatch)
        self.assertEqual(r["incumbent_specialist"]["status"],
                         "SPECIALIST_ITEM_IDENTITY_MISMATCH")
        self.assertIsNone(r["incumbent_specialist"]["departure_epoch"])

    def test_out_of_order_restock_chain_rejected(self):
        bad=[cycle(1,restock=6000,upper=6200,target=6300,
                   depleted=7200),
             cycle(2,restock=3000,upper=3250,target=3300,
                   depleted=4200)]
        r=run(bad)
        self.assertEqual(r["status"],"INVALID_OR_UNSORTED_RESTOCK_CHAIN")
        self.assertIsNone(r["first_reachable"])

    def test_absent_forecast_does_not_invent_restocks(self):
        r=run([])
        self.assertEqual(r["status"],"NO_V2_CYCLES")
        self.assertIsNone(r["next_predicted_restock"])
        self.assertIsNone(r["first_reachable"])

    def test_full_24_contract_renders_with_no_simulated_accuracy(self):
        from research.v128_full24_earliest_shadow import exact_roster
        keys=exact_roster()
        self.assertEqual(len(keys),24)
        for key in keys:
            country,item=key.split(":",1)
            with self.subTest(item=key):
                r=build_item_timeline(key,{"predictions":[]},now=NOW,
                    issued_at=NOW-20,stock_as_of=NOW-30)
                self.assertEqual(r["item_key"],key)
                self.assertEqual(r["status"],"NO_V2_CYCLES")
                self.assertFalse(r["source_country_freshness_verified"])
                self.assertFalse(r["stock_at_arrival_at_least_30_verified"])

if __name__ == "__main__":
    unittest.main()
