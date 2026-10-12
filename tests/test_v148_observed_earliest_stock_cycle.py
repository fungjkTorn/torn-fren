"""V148 earliest reachable >=30-stock intervals for long PI+pilot flights."""
import unittest

from research.plushie_champions.common import TRAVEL_SECONDS
from research.v107_explicit_restock_cycle_baseline import StockObservation as O
from research.v145_provider_continuous_phases import provider_continuous_phases
from research.v148_observed_earliest_stock_cycle import first_reachable_stock_cycles

T=1791800000


def trace(*,n=10,high=900,low=900,provider_churn=True):
    t=T
    obs=[O(t,0,"yata")]
    for i in range(n):
        t+=low
        obs.append(O(t,150,"yata"))
        if provider_churn:
            obs.append(O(t+60,120,"prometheus"))
            obs.append(O(t+120,110,"yata"))
        t+=high
        obs.append(O(t,0,"yata"))
    return obs,t


def propose(country="uni", *, n=10, high=900,low=900,asof_offset=0,
            max_cycles=16):
    samples,end=trace(n=n,high=high,low=low)
    asof=end+asof_offset
    data=provider_continuous_phases(samples,asof=asof)
    return first_reachable_stock_cycles(
        country+":Nessie Plushie",data,asof=asof,max_cycles=max_cycles)


class FirstReachableStockWindowsTests(unittest.TestCase):
    def test_106min_flight_reaches_next_reasonable_plushie_cycle(self):
        r=propose("uni")
        target=r["first_reachable"]
        self.assertEqual(r["status"],"PROVISIONAL_FIRST_REACHABLE_STOCK_WINDOW")
        # Three earlier 30-minute cycles cannot be reached from 106min out.
        self.assertEqual(target["cycle_number"],4)
        self.assertEqual(target["earliest_departure_epoch"],r["issued_epoch"])
        self.assertEqual(target["arrival_epoch"],r["issued_epoch"]+6360)
        self.assertEqual(r["observed_median_restock_cadence_seconds"],1800)
        self.assertFalse(r["long_wait_despite_short_cadence"])
        self.assertFalse(r["safe_to_fly_certified"])
        self.assertIsNone(r["calibrated_stock30_probability"])

    def test_south_africa_long_flight_needs_beyond_p4(self):
        r=propose("sou")
        self.assertEqual(r["first_reachable"]["cycle_number"],7)
        self.assertEqual(r["first_reachable"]["wait_seconds"],0)
        self.assertEqual(r["travel_seconds"],11820)
        self.assertGreaterEqual(len(r["projected_windows"]),7)

    def test_17min_flight_skips_p1_and_chooses_p2(self):
        r=propose("mex",low=600,high=300)
        target=r["first_reachable"]
        self.assertGreaterEqual(target["cycle_number"],2)
        self.assertGreaterEqual(target["arrival_epoch"],target["late_start_epoch"])
        self.assertLess(target["arrival_epoch"],target["early_end_epoch"])
        self.assertEqual(r["observed_median_restock_cadence_seconds"],900)

    def test_all_11_flight_times_reach_a_cycle_without_long_wait(self):
        for country in TRAVEL_SECONDS:
            with self.subTest(country=country):
                r=propose(country)
                target=r["first_reachable"]
                self.assertIsNotNone(target)
                self.assertLessEqual(target["wait_seconds"],1800)
                self.assertFalse(r["safe_to_fly_certified"])

    def test_one_completed_period_of_each_kind_is_history_not_certification(self):
        samples,t=trace(n=2)
        history=provider_continuous_phases(samples,asof=t)
        out=first_reachable_stock_cycles("mex:Jaguar Plushie",history,asof=t)
        self.assertEqual(out["historical_evidence_tier"],
                         "BOUNDED_HISTORY_SPARSE_PROVISIONAL")
        self.assertIsNotNone(out["first_reachable"])
        self.assertFalse(out["safe_to_fly_certified"])
        self.assertFalse(out["first_reachable"]["stock_ge_30_on_arrival_verified"])

    def test_no_timing_when_current_onset_missing(self):
        obs=[O(T,0,"yata"), O(T+800,160,"prometheus")]
        ph=provider_continuous_phases(obs,asof=T+800)
        result=first_reachable_stock_cycles("mex:Jaguar Plushie",
                                             ph,asof=T+800)
        self.assertIsNone(result["first_reachable"])
        self.assertEqual(result["status"],"NO_ENOUGH_BOUNDED_HISTORY")

    def test_stale_or_unknown_current_phase_yields_no_departure(self):
        obs,t=trace(n=5)
        p=provider_continuous_phases(obs,asof=t)
        p["phase_onset"]=None
        r=first_reachable_stock_cycles("uni:Nessie Plushie",p,asof=t)
        self.assertIsNone(r["first_reachable"])
        self.assertEqual(r["status"],"CURRENT_STATE_ONSET_NOT_VERIFIABLE")

    def test_short_stocked_duration_with_large_late_restock_band_is_not_safe(self):
        obs,t=trace(n=5,high=120,low=7200)
        p=provider_continuous_phases(obs,asof=t)
        # Deliberately widen empirical depleted duration spread while
        # preserving all past events and disallowing invented guarantees.
        p["depleted_durations"]=[300,600,1200,2400,7200]
        r=first_reachable_stock_cycles("uni:Nessie Plushie",p,asof=t)
        self.assertIsNone(r["first_reachable"])
        self.assertEqual(r["status"],"NO_CONSERVATIVE_REACHABLE_WINDOW")
        self.assertGreater(r["skipped_cycles_by_reason"].get(
            "UNCERTAINTY_WINDOWS_DO_NOT_OVERLAP",0),0)

    def test_no_future_data_in_stock_window_builder(self):
        obs,t=trace(n=8)
        p=provider_continuous_phases(obs,asof=t)
        with self.assertRaises(ValueError):
            provider_continuous_phases(obs,asof=t-1)
        r=first_reachable_stock_cycles("uni:Nessie Plushie",p,asof=t)
        self.assertTrue(all(win["expected_start_epoch"]>=t
                            for win in r["projected_windows"]))
        self.assertTrue(r["first_reachable"]["provisional"])

if __name__=="__main__":
    unittest.main()
