"""Pure source-log regression for V139 proxy evidence: no DB, no VM."""
from __future__ import annotations

import json
import unittest

from research.v139_beta_evidence_summary import summarize

ITEMS = [
    ("arg:Ceibo Flower",4,0),("arg:Monkey Plushie",7,3),
    ("can:Crocus",5,0),("can:Wolverine Plushie",9,4),
    ("can:Xanax",5,1),("cay:Banana Orchid",4,0),
    ("cay:Stingray Plushie",6,8),("chi:Panda Plushie",6,4),
    ("chi:Peony",0,0),("haw:Orchid",5,0),
    ("jap:Cherry Blossom",5,2),("jap:Xanax",0,0),
    ("mex:Dahlia",3,1),("mex:Jaguar Plushie",16,0),
    ("sou:African Violet",4,0),("sou:Lion Plushie",10,4),
    ("swi:Chamois Plushie",5,4),("swi:Edelweiss",0,0),
    ("uae:Camel Plushie",5,7),("uae:Tribulus Omanense",3,0),
    ("uni:Heather",5,0),("uni:Nessie Plushie",6,6),
    ("uni:Red Fox Plushie",9,3),("uni:Xanax",0,0),
]


def fixture(*,broken=None):
    def line(header, value):
        return header + json.dumps(value,sort_keys=True)
    graph = {"mean_absolute_restock_error_minutes":130.05,
             "observed_restock_window_hit_rate":.3604,
             "arrival_inside_target_cycle_rate":.3062}
    v75 = {
        "matched_flight_outcomes":814,"matched_both_stocked":554,
        "matched_only_old_model_stocked":152,
        "matched_only_leave_now_stocked":67,
        "matched_both_below_30":41,
        "valid_departure_proposals":1028,
        "no_valid_departure_or_abstention":16,
        "first_item_UTC_hourly_starts":1044,
        "old_model_arrival_stock_at_least_30":761,
        "old_model_arrival_stock_below_30":111,
        "old_model_arrival_unknown_or_pending":156,
    }
    v128 = {
        "matched_pair":{"both_scorable":160,"both_hit":102,
                        "model_only_hit":14,"now_only_hit":12,
                        "both_miss":32},
        "proposed_departure_hours":198,"abstained_hours":306,
        "first_issue_UTC_item_hours":504,
        "model_proxy_success":122,"model_proxy_miss":47,
        "model_proxy_unknown":29,"lower_bound_hits_per_start":.2421
    }
    v2 = {
        "matched_ui_vs_leave_now":2013,
        "matched_ui_stocked_fraction":.6557,
        "matched_leave_now_stocked_fraction":.615,
        "matched_only_ui_stocked":423,
        "matched_only_leave_now_stocked":341,
        "ui_minus_leave_now_only_known_pairs":82
    }
    timing = {
        "issued_five_minute_snapshots":5736,
        "unchanged_collector_state_pairs_with_two_departures":835,
        "same_observed_state_absolute_departure_shift_gt_15min":70
    }
    if broken == "v128_mismatch": v128["model_proxy_miss"]+=1
    lines=[
        "===== V135 ONE-PASS OVERNIGHT RESEARCH EVIDENCE =====",
        line("Original graph restock/cycle accuracy: ",graph),
        line("V75 versus leave now, first-item-UTC-hour: ",v75),
        line("V128 observed arrival stock and matched leave-now: ",v128),
        line("V128 latest time-to-leave coverage/forecast shifts: ",timing),
        "===== ITEM-BY-ITEM CHECKPOINT =====",
    ]
    for item,hit,miss in ITEMS:
        row={"v128_model_stocked":hit, "v128_model_below30":miss,
             "v128_mature_stock_proxies":hit+miss,
             "v128_future_watches":3,"v128_watch_reconfirmed":1,
             "v75_matched_flights":25,
             "v75_model_only_vs_leave_now_only_net":1,
             "old_v2_restock_window_hit_fraction":.3,
             "old_v2_valid_restock_cycles":20}
        lines.append(line(item+" ",row))
    lines.extend([
        "===== V138 CAUTION =====",
        line("Original V2 earliest displayed departure versus leave-now: ",v2),
        "===== ORIGINAL V2 DIRECT ARRIVAL BY ITEM =====",
    ])
    for item,_,_ in ITEMS:
        if item=="haw:Orchid": continue
        lines.append(line(item+" ",{
            "matched":10,"ui_only_minus_now_only":0}))
    if broken != "missing_completion":
        lines.append("===== AUDIT DONE, NO MODEL OR DATABASE CHANGES =====")
    return "\n".join(lines)+"\n"


class V139BetaEvidenceTests(unittest.TestCase):
    def test_saved_v139_outcome_counts_and_mismatched_cohorts(self):
        out=summarize(fixture())
        self.assertEqual(len(out["items"]),24)
        self.assertEqual(out["v75"]["matched"]["net_win_count"],85)
        self.assertEqual(out["v75"]["matched"]["model_success_fraction"],.8673)
        self.assertEqual(out["v75"]["matched"]["leave_now_success_fraction"],.7629)
        self.assertEqual(out["v75"]["proposal_fraction"],.9847)
        self.assertEqual(out["v128"]["matched"]["net_win_count"],2)
        self.assertEqual(out["v128"]["matched"]["model_success_fraction"],.725)
        self.assertEqual(out["v128"]["matched"]["leave_now_success_fraction"],.7125)
        self.assertEqual(out["v128"]["proposal_fraction"],.3929)
        self.assertEqual(out["v128"]["lower_bound_hit_fraction_per_start"],.2421)
        self.assertEqual(out["original_v2"]["matched"]["net_win_count"],82)
        self.assertEqual(out["original_v2"]["restock_mean_absolute_error_minutes"],130.05)
        self.assertTrue(out["unverified"]["same_three_way_issue_cohort"])
        self.assertTrue(all(not row["ready_for_promotion"] for row in out["items"]))

    def test_per_item_problem_labels(self):
        out=summarize(fixture())
        items={x["item_key"]:x for x in out["items"]}
        self.assertEqual(items["uae:Camel Plushie"]["first_diagnostic"],
                         "V128_HIGH_OBSERVED_MISS_FRACTION")
        self.assertEqual(items["cay:Stingray Plushie"]["first_diagnostic"],
                         "V128_HIGH_OBSERVED_MISS_FRACTION")
        self.assertEqual(items["uni:Nessie Plushie"]["first_diagnostic"],
                         "V128_HIGH_OBSERVED_MISS_FRACTION")
        self.assertEqual(items["jap:Xanax"]["first_diagnostic"],
                         "NO_V128_MATURED_ARRIVALS")
        self.assertEqual(items["mex:Jaguar Plushie"]["v128_success_given_scorable"],
                         1.0)
        self.assertFalse(items["mex:Jaguar Plushie"]["ready_for_promotion"])

    def test_partial_or_inconsistent_evidence_rejected(self):
        for variant in ("missing_completion","v128_mismatch"):
            with self.subTest(variant=variant),self.assertRaises(ValueError):
                summarize(fixture(broken=variant))

    def test_duplicate_item_rejected(self):
        text=fixture()
        first=next(line for line in text.splitlines()
                   if line.startswith("arg:Ceibo Flower {"))
        # Inserting within the per-item section violates uniqueness.
        text=text.replace(first,first+"\n"+first)
        with self.assertRaisesRegex(ValueError,"duplicate"):
            summarize(text)


if __name__ == "__main__":
    unittest.main()
