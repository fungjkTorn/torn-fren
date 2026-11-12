"""V107 restock cycle regressions: no lookahead, threshold and flight math."""
import unittest

from research.v107_explicit_restock_cycle_baseline import (
    StockObservation,completed_phases,next_windows
)

BASE=1_700_000_000


def cycles(n=8, *, high=300, low=500, source="yata"):
    # Ends with a known depleted phase, no future reopening yet.
    rows=[StockObservation(BASE,0,source)]
    t=BASE
    for i in range(n):
        t+=low
        rows.append(StockObservation(t,200,source))
        t+=high
        rows.append(StockObservation(t,0,source))
    return rows


class ExplicitCycleTests(unittest.TestCase):
    def test_completed_phases_count_both_threshold_directions(self):
        events=cycles(n=8)
        result=completed_phases(events,asof=events[-1].epoch+100)
        self.assertEqual(len(result["stocked_durations"]),8)
        self.assertEqual(len(result["depleted_durations"]),7)
        self.assertTrue(all(v==300 for v in result["stocked_durations"]))
        self.assertTrue(all(v==500 for v in result["depleted_durations"]))
        self.assertEqual(result["phase"],"LOW")
        self.assertEqual(result["phase_onset"],events[-1].epoch)

    def test_next_restocks_not_arbitrary_wait_when_next_stock_cannot_be_reached(self):
        obs=cycles(n=8)
        q=obs[-1].epoch+100
        result=next_windows("mex:Jaguar Plushie",obs,asof=q)
        self.assertEqual(result["status"],"FORECAST_AVAILABLE")
        self.assertEqual(len(result["windows"]),4)
        first=result["windows"][0]
        self.assertEqual(first["expected_stocked_start"],q+400)
        self.assertEqual(first["expected_drop_below_30"],q+700)
        # Mexico flight takes 1020s; first restock window would be missed.
        self.assertIsNone(first["earliest_expected_departure"])
        # Next restock opens later; earliest departure is derived from
        # restock time minus the actual flight duration.
        second=result["windows"][1]
        self.assertEqual(second["expected_stocked_start"],q+1200)
        self.assertEqual(second["earliest_expected_departure"],q+180)
        self.assertEqual(second["expected_arrival"],q+1200)

    def test_future_rows_never_change_asof_prediction(self):
        original=cycles(n=8)
        q=original[-1].epoch+100
        future=[
            StockObservation(q+500,999,"yata"),
            StockObservation(q+800,0,"yata"),
            StockObservation(q+1000,5000,"yata"),
        ]
        a=next_windows("mex:Jaguar Plushie",original,asof=q)
        b=next_windows("mex:Jaguar Plushie",original+future,asof=q)
        self.assertEqual(a,b)

    def test_scarce_completed_cycles_abstain(self):
        obs=cycles(n=3)
        q=obs[-1].epoch+100
        result=next_windows("mex:Jaguar Plushie",obs,asof=q)
        self.assertEqual(result["status"],"ABSTAIN_INSUFFICIENT_COMPLETED_CYCLES")
        self.assertEqual(result["windows"],[])

    def test_unknown_phase_start_abstains(self):
        rows=[StockObservation(BASE,200,"yata")]
        result=next_windows("mex:Jaguar Plushie",rows,asof=BASE+100)
        self.assertEqual(result["status"],"ABSTAIN_PHASE_START_UNKNOWN")

    def test_overstale_source_abstains(self):
        obs=cycles(n=8)
        result=next_windows(
            "mex:Jaguar Plushie",obs,asof=obs[-1].epoch+86401)
        self.assertEqual(result["status"],"ABSTAIN_STALE_OR_MISSING_STOCK")

    def test_current_stocked_phase_can_recommend_leave_now(self):
        rows=cycles(n=8)
        t=rows[-1].epoch
        rows.append(StockObservation(t+500,200,"yata"))
        # For an extended-duration fixture, use artificially longer
        # stock phases so Mexico flight can arrive before depletion.
        long=cycles(n=8,high=2400,low=500)
        base=long[-1].epoch+500
        long.append(StockObservation(base,1500,"yata"))
        q=base+100
        result=next_windows("mex:Jaguar Plushie",long,asof=q)
        self.assertEqual(result["status"],"FORECAST_AVAILABLE")
        self.assertEqual(
            result["windows"][0]["earliest_expected_departure"],q)
        self.assertGreater(
            result["windows"][0]["expected_drop_below_30"],q+1020)

    def test_collection_gaps_invalidate_spanning_phase_durations(self):
        obs=cycles(n=8)
        a=obs[3].epoch-10
        b=obs[4].epoch+10
        clean=completed_phases(obs,asof=obs[-1].epoch+100)
        corrupted=completed_phases(
            obs,asof=obs[-1].epoch+100,
            collection_gaps=[(a,b)])
        self.assertLess(
            len(corrupted["stocked_durations"])
            +len(corrupted["depleted_durations"]),
            len(clean["stocked_durations"])
            +len(clean["depleted_durations"]))

    def test_provider_switch_never_stitches_durations(self):
        obs=cycles(n=8)
        mixed=obs[:8]+[
            StockObservation(v.epoch,v.quantity,"prometheus")
            for v in obs[8:]]
        clean=completed_phases(obs,asof=obs[-1].epoch+100)
        change=completed_phases(mixed,asof=obs[-1].epoch+100)
        self.assertLess(
            len(change["depleted_durations"]),
            len(clean["depleted_durations"]))

    def test_invalid_item_or_no_prior_evidence_fails_closed(self):
        with self.assertRaises(ValueError):
            next_windows("mars:Xanax",cycles(8),asof=BASE+1)
        result=next_windows("mex:Jaguar Plushie",[],asof=BASE)
        self.assertEqual(result["status"],"ABSTAIN_STALE_OR_MISSING_STOCK")


if __name__=="__main__":
    unittest.main()
