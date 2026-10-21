"""Existing experimental page: 24-item safe compatibility bridge tests."""
import copy
import unittest
from research import v140_existing_experimental_beta_board as m

N = 1791800000
KEYS = ("arg:Ceibo Flower","arg:Monkey Plushie","can:Crocus",
"can:Wolverine Plushie","can:Xanax","cay:Banana Orchid",
"cay:Stingray Plushie","chi:Panda Plushie","chi:Peony","haw:Orchid",
"jap:Cherry Blossom","jap:Xanax","mex:Dahlia","mex:Jaguar Plushie",
"sou:African Violet","sou:Lion Plushie","swi:Chamois Plushie",
"swi:Edelweiss","uae:Camel Plushie","uae:Tribulus Omanense",
"uni:Heather","uni:Nessie Plushie","uni:Red Fox Plushie","uni:Xanax")

def old(k, departure=N+600, valid=N+280, stock=N-15):
    return dict(item_key=k,model_family="champion",model_config="selected",
                status="RESEARCH_PROPOSAL_ONLY",actionable=True,
                prediction_accuracy_verified=False,computed_at=N-20,
                stock_as_of=stock,valid_until=valid,departure=departure,
                arrival=departure+6360)

def candidate(k, issue=N-20, dep=N+1200):
    return dict(item_key=k,research_only=True,
                display_status="RESEARCH_FUTURE_WATCH_RECHECK_REQUIRED",
                forecast_issued_epoch=issue,proposed_departure_epoch=dep,
                proposed_arrival_epoch=dep+6360,message="research",
                simulation_arrival_fraction_not_calibrated_probability=.66)

def panel(rows=None):
    return dict(status="V133_SAFE_RESEARCH_24_ITEM_DEPARTURE_PANEL_DATA",
                roster_size=24,selected_issued_epoch=N-20,
                items=rows if rows is not None else {k:candidate(k) for k in KEYS})

def build(old_rows=None, p=None):
    return m.build_board(dict(latest=old_rows or []),
                         panel() if p is None else p,now=N,roster_keys=KEYS)

class BridgeTests(unittest.TestCase):
    def test_full_24_preserves_baseline_and_v2_graph(self):
        source=[old(k) for k in KEYS]
        clone=copy.deepcopy(source)
        report=build(source)
        self.assertEqual(report["roster_count"],24)
        self.assertTrue(report["legacy_complete_24"])
        self.assertTrue(report["v128_complete_24"])
        self.assertEqual(source,clone)
        item=next(x for x in report["rows"] if x["item_key"]=="arg:Monkey Plushie")
        self.assertEqual(item["existing_experimental_model"]["model_family"],"champion")
        self.assertEqual(item["v128_research_challenger"]["model_family"],"V128")
        self.assertIn("item=Monkey+Plushie",item["graph_url"])
        self.assertFalse(item["stock_at_landing_verified"])
    def test_original_21_retained_and_three_absent_explicit(self):
        missing={"chi:Panda Plushie","sou:Lion Plushie","jap:Xanax"}
        report=build([old(k) for k in KEYS if k not in missing])
        self.assertEqual(report["legacy_unique_usable_keys"],21)
        self.assertFalse(report["legacy_complete_24"])
        for row in report["rows"]:
            if row["item_key"] in missing:
                self.assertFalse(row["existing_experimental_model"]["present"])
                self.assertIsNone(row["existing_experimental_model"]["departure_epoch"])
    def test_expired_incumbent_and_future_watch(self):
        report=build([old(KEYS[0],valid=N-1),old(KEYS[1],departure=N+21600)])
        a,b=report["rows"][:2]
        self.assertEqual(a["existing_experimental_model"]["display_state"],"EXPIRED_SNAPSHOT")
        self.assertIsNone(a["existing_experimental_model"]["departure_epoch"])
        self.assertEqual(b["existing_experimental_model"]["display_state"],"FUTURE_FORECAST_WATCH")
        self.assertEqual(b["existing_experimental_model"]["refresh_due_in_seconds"],280)
    def test_v128_stale_and_incomplete_hidden(self):
        stale=panel({k:candidate(k,issue=N-301) for k in KEYS})
        stale["selected_issued_epoch"]=N-301
        result=build([old(k) for k in KEYS],stale)
        self.assertTrue(all(x["v128_research_challenger"]["departure_epoch"] is None for x in result["rows"]))
        broken=panel()
        del broken["items"][KEYS[0]]
        result=build([old(k) for k in KEYS],broken)
        self.assertFalse(result["v128_complete_24"])
        self.assertTrue(all(x["v128_research_challenger"]["departure_epoch"] is None for x in result["rows"]))
    def test_stale_collector_suppresses_incumbent_departure(self):
        a=build([old(KEYS[0],stock=N-601)])["rows"][0]
        self.assertEqual(a["existing_experimental_model"]["display_state"],"UNVERIFIED_SOURCE_FRESHNESS")
        self.assertIsNone(a["existing_experimental_model"]["departure_epoch"])
    def test_passed_candidate_and_duplicate_legacy(self):
        p=panel({k:candidate(k,dep=N-2) for k in KEYS})
        x=build([old(KEYS[0]),old(KEYS[0])],p)
        self.assertEqual(x["legacy_duplicate_item_keys"],[KEYS[0]])
        self.assertFalse(x["rows"][0]["existing_experimental_model"]["present"])
        self.assertTrue(all(r["v128_research_challenger"]["departure_epoch"] is None for r in x["rows"]))
    def test_provisional_never_certified(self):
        result=build([old(k) for k in KEYS])
        for r in result["rows"]:
            self.assertFalse(r["existing_experimental_model"]["verified_departure"])
            self.assertFalse(r["v128_research_challenger"]["verified_departure"])
    def test_bad_roster(self):
        with self.assertRaises(ValueError):
            m.build_board({},panel(),now=N,roster_keys=KEYS[:-1]+(KEYS[0],))
    def test_mixed_issuance_rejected_for_whole_batch(self):
        p=panel()
        p["items"][KEYS[0]]["forecast_issued_epoch"]=N-100
        r=build([old(k) for k in KEYS],p)
        self.assertFalse(r["v128_complete_24"])
        self.assertTrue(all(x["v128_research_challenger"]["departure_epoch"] is None for x in r["rows"]))
    def test_missing_v128_preserves_incumbent(self):
        r=build([old(k) for k in KEYS],{})
        self.assertTrue(r["legacy_complete_24"])
        self.assertFalse(r["v128_complete_24"])
        self.assertTrue(all(x["v128_research_challenger"]["departure_epoch"] is None for x in r["rows"]))

if __name__=="__main__":
    unittest.main()
