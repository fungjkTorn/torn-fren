"""V151 earliest-first, same-history deterministic stock-at-arrival scenarios."""
import unittest
from copy import deepcopy

from research.plushie_champions.common import TRAVEL_SECONDS
from research.v107_explicit_restock_cycle_baseline import StockObservation
from research.v145_provider_continuous_phases import provider_continuous_phases
from research.v151_stable_earliest_departure import stable_earliest_departure

T=1791800000


def history(*,high=900,low=900,n=12,source_switch=True):
    obs=[StockObservation(T,0,"yata")]
    t=T
    for _ in range(n):
        t+=low
        obs.append(StockObservation(t,100,"yata"))
        if source_switch:
            obs.extend((
                StockObservation(t+100,90,"prometheus"),
                StockObservation(t+200,85,"yata"),
            ))
        t+=high
        obs.append(StockObservation(t,0,"yata"))
    return provider_continuous_phases(obs,asof=t), t


class StableEarliestTests(unittest.TestCase):
    def test_all_country_flight_times_including_japan_long_route(self):
        previous,issued=history()
        for country in TRAVEL_SECONDS:
            with self.subTest(country=country):
                r=stable_earliest_departure(
                    country+":Test Stock",previous,asof=issued,scenarios=48)
                self.assertIsNotNone(r["first_reachable"])
                self.assertLessEqual(r["first_reachable"]["wait_seconds"],1800)
                self.assertEqual(r["first_reachable"]["arrival_epoch"],
                                 issued+TRAVEL_SECONDS[country]+
                                 r["first_reachable"]["wait_seconds"])
                self.assertEqual(r["first_reachable"]["scenario_stock_fraction"],1.0)
                self.assertEqual(r["median_observed_restock_cadence_seconds"],1800)
                self.assertFalse(r["game_stock30_at_arrival_verified"])

    def test_earliest_supported_future_bin_not_later_high_scoring_bin(self):
        previous,issued=history(high=900,low=1200)
        r=stable_earliest_departure(
            "mex:Jaguar Plushie",previous,asof=issued,scenarios=64)
        self.assertEqual(r["score_now"],0)
        self.assertEqual(r["first_reachable"]["wait_seconds"],300)
        self.assertEqual(r["first_reachable"]["status"],"RESEARCH_SOON_RECONFIRM")
        self.assertEqual(r["median_observed_restock_cadence_seconds"],2100)
        self.assertFalse(r["first_reachable"]["scenario_fraction_calibrated_probability"])

    def test_identical_completed_history_stable_seed_five_minutes_later(self):
        old,issued=history(high=900,low=900)
        now=stable_earliest_departure(
            "jap:Xanax",old,asof=issued,scenarios=96)
        after=stable_earliest_departure(
            "jap:Xanax",old,asof=issued+300,scenarios=96)
        repeat=stable_earliest_departure(
            "jap:Xanax",old,asof=issued,scenarios=96)
        self.assertEqual(now,repeat)
        self.assertEqual(
            now["first_next_restock_onset_median_seconds"],
            after["first_next_restock_onset_median_seconds"]+300)
        self.assertEqual(
            now["issued_epoch"]+
              now["first_next_restock_onset_median_seconds"],
            after["issued_epoch"]+
              after["first_next_restock_onset_median_seconds"])

    def test_single_observed_bounded_high_low_is_real_sparse_history(self):
        previous,issued=history(n=2,source_switch=True)
        r=stable_earliest_departure(
            "uni:Nessie Plushie",previous,asof=issued,scenarios=32)
        self.assertEqual(r["history_tier"],"BOUNDED_HISTORY_SPARSE_PROVISIONAL")
        self.assertIsNotNone(r["first_reachable"])
        self.assertTrue(r["forward_performance_untested"])

    def test_sub_five_minute_stock_lifetime_kept_as_one_bin_research_signal(self):
        previous,issued=history(n=6,high=200,low=600,source_switch=False)
        r=stable_earliest_departure(
            "jap:Xanax",previous,asof=issued,scenarios=32)
        self.assertIsNone(r["first_reachable"])
        self.assertEqual(r["status"],"NO_TWO_BIN_SUPPORTED_DEPARTURE")
        self.assertIsNotNone(r["secondary_research_signal"])
        self.assertTrue(r["secondary_research_signal"]["not_actionable"])
        self.assertTrue(r["diagnostic"][
            "short_stocked_phases_may_not_survive_five_minutes"])

    def test_no_fake_result_if_phase_onset_unknown(self):
        previous,issued=history()
        previous["phase_onset"]=None
        r=stable_earliest_departure(
            "chi:Peony",previous,asof=issued,scenarios=32)
        self.assertEqual(r["status"],"CURRENT_PHASE_OR_SOURCE_UNKNOWN")
        self.assertIsNone(r["first_reachable"])

    def test_conditional_phase_source_gap_does_not_fake_intervals(self):
        previous,issued=history()
        previous["last_observation"]=StockObservation(issued,100,"yata")
        r=stable_earliest_departure(
            "mex:Jaguar Plushie",previous,asof=issued,scenarios=32)
        self.assertEqual(r["status"],"INCONSISTENT_LAST_STOCK_PHASE")
        self.assertIsNone(r["first_reachable"])

    def test_bound_scenarios_and_reject_future_data(self):
        previous,issued=history()
        for kwargs in (
            {"scenarios":257},{"scenarios":0},{"score_floor":0},
            {"asof":issued-1}
        ):
            with self.subTest(kwargs=kwargs):
                if kwargs.get("asof") is not None:
                    r=stable_earliest_departure(
                        "uni:Nessie Plushie",previous,
                        scenarios=32,**kwargs)
                    self.assertEqual(r["status"],"CURRENT_PHASE_OR_SOURCE_UNKNOWN")
                else:
                    with self.assertRaises(ValueError):
                        stable_earliest_departure(
                            "uni:Nessie Plushie",previous,asof=issued,**kwargs)
        with self.assertRaises(ValueError):
            stable_earliest_departure(
                "uni:Nessie Plushie",previous,asof=issued,
                scenarios=32,score_floor=1.1)

if __name__=="__main__":
    unittest.main()
