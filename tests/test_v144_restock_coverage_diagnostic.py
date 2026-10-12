"""V144 read-only audit of 24h restock changes versus model abstentions."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research import v144_restock_coverage_diagnostic as m
from research.v128_full24_earliest_shadow import exact_roster

NOW=1791800000


class PureTransitionsTests(unittest.TestCase):
    def test_pinned_vm_diagnostic_roster_equals_exact_model_roster(self):
        self.assertEqual(m.KEYS,set(exact_roster()))

    def test_clean_replenishments_visible_despite_other_model_abstention(self):
        # Several genuine observed high/low transitions are different from
        # V128 being eligible to issue an arrival estimate today.
        rows=[
            (NOW-70000,0,"yata"),(NOW-68000,100,"yata"),
            (NOW-66000,0,"yata"),(NOW-65000,100,"yata"),
            (NOW-63000,0,"yata"),(NOW-62000,100,"yata"),
            (NOW-60000,0,"yata"),(NOW-59000,100,"yata"),
            (NOW-57000,0,"yata"),(NOW-56000,100,"yata"),
            (NOW-54000,0,"yata"),(NOW-53000,100,"yata"),
            (NOW-52000,100,"prometheus"),
        ]
        out=m.event_diagnostic(rows,asof=NOW,earliest=NOW-m.DAY)
        self.assertEqual(out["observed_clean_crossings_to_30"],6)
        self.assertEqual(out["observed_clean_zero_to_positive"],6)
        self.assertEqual(out["provider_switch_count"],1)
        self.assertEqual(out["ambiguous_crossings_to_30_source_or_gap"],0)
        self.assertTrue(out["cadence_is_based_on_three_or_more_events"])
        self.assertFalse(out["country_source_freshness_verified"])

    def test_positive_increase_without_crossing_30_is_not_silent(self):
        rows=[(NOW-4000,60,"yata"),(NOW-2500,120,"yata"),
              (NOW-2000,65,"yata"),(NOW-1000,115,"yata")]
        out=m.event_diagnostic(rows,asof=NOW,earliest=NOW-m.DAY)
        self.assertEqual(out["observed_clean_crossings_to_30"],0)
        self.assertEqual(out["observed_positive_quantity_jumps_same_source"],2)
        self.assertEqual(out["positive_jumps_without_dropping_below_30"],2)
        self.assertTrue(out["positive_quantity_jump_is_not_certified_restock"])

    def test_switch_or_gap_does_not_certify_a_restock(self):
        rows=[
            (NOW-3600,0,"yata"),(NOW-3400,99,"prometheus"),
            (NOW-1800,0,"prometheus"),(NOW-1600,100,"prometheus"),
            (NOW-1400,0,"prometheus"),(NOW-1200,100,"prometheus"),
        ]
        observed=m.event_diagnostic(rows,asof=NOW,earliest=NOW-m.DAY,
                                    gaps=[(NOW-1550,NOW-1350)])
        self.assertEqual(observed["ambiguous_crossings_to_30_source_or_gap"],2)
        self.assertEqual(observed["observed_clean_crossings_to_30"],1)
        self.assertEqual(observed["provider_switch_count"],1)
        self.assertIsNone(observed["median_between_clean_30_crossings_seconds"])

    def test_future_or_unordered_changes_rejected(self):
        for rows in ([(NOW+1,40,"yata")],
                     [(NOW-1,0,"yata"),(NOW-2,50,"yata")]):
            with self.assertRaises(ValueError):
                m.event_diagnostic(rows,asof=NOW,earliest=NOW-m.DAY)


class Full24ReadonlyDiagnosticTests(unittest.TestCase):
    def test_day_of_recorded_restocks_with_zero_accepted_model_issue(self):
        with tempfile.TemporaryDirectory() as folder:
            stock=Path(folder)/"collector.db"
            sidecar=Path(folder)/"shadow.db"
            keys=exact_roster()
            with sqlite3.connect(stock) as db:
                db.execute("""CREATE TABLE stock_history(
                    id INTEGER PRIMARY KEY,timestamp INTEGER,
                    country TEXT,item_name TEXT,quantity INTEGER,source TEXT
                )""")
                db.execute("""CREATE TABLE collection_gaps(
                    start_timestamp INTEGER,end_timestamp INTEGER
                )""")
                japan=[(NOW-60000,0),(NOW-58000,100),
                       (NOW-56000,0),(NOW-54000,100),
                       (NOW-52000,0),(NOW-50000,100),
                       (NOW-48000,0),(NOW-46000,100),
                       (NOW-44000,0),(NOW-42000,100),
                       (NOW-40000,0),(NOW-38000,100)]
                for when,qty in japan:
                    db.execute("""INSERT INTO stock_history(
                      timestamp,country,item_name,quantity,source)
                      VALUES (?,?,?,?,?)""",
                      (when,"jap","Xanax",qty,"yata"))
            with sqlite3.connect(sidecar) as db:
                db.execute("""CREATE TABLE v128_issued(
                    item_key TEXT,issued_epoch INTEGER,
                    source_status TEXT,decision_status TEXT
                )""")
                for key in keys:
                    for ago in (3600,1200):
                        db.execute(
                            "INSERT INTO v128_issued VALUES(?,?,?,?)",
                            (key,NOW-ago,"CURRENT_PHASE_ONSET_UNKNOWN",
                             "ABSTAIN_CURRENT_PHASE_ONSET_UNKNOWN"))
            # Saving/restoring file byte signatures catches accidental writes.
            original=(stock.read_bytes(),sidecar.read_bytes())
            out=m.diagnose(collector=stock,sidecar=sidecar,now=NOW)
            self.assertEqual(out["exact_item_count"],24)
            self.assertTrue(out["all24_present"])
            jap=out["items"]["jap:Xanax"]
            self.assertEqual(jap["observed_clean_crossings_to_30"],6)
            self.assertEqual(jap["v128_issue_ticks_last_day"],2)
            self.assertEqual(jap["v128_accepted_departure_ticks"],0)
            self.assertEqual(jap["v128_abstained_or_unsupported_ticks"],2)
            self.assertEqual(jap["last_v128_issue"]["decision_status"],
                             "ABSTAIN_CURRENT_PHASE_ONSET_UNKNOWN")
            self.assertIsNotNone(jap["median_between_clean_30_crossings_seconds"])
            self.assertFalse(out["databases_modified"])
            self.assertEqual(stock.read_bytes(),original[0])
            self.assertEqual(sidecar.read_bytes(),original[1])

    def test_source_and_sidecar_identity_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"x.db"
            sqlite3.connect(db).close()
            with self.assertRaises(ValueError):
                m.diagnose(collector=db,sidecar=db,now=NOW)


if __name__=="__main__":
    unittest.main()
