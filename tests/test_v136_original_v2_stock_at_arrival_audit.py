"""Tests for V136 original V2 >=30 stock-at-arrival benchmark."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research import v136_original_v2_stock_at_arrival_audit as m

T0 = (1790000000 // 3600) * 3600
UK = m.TRAVEL_SECONDS["uni"]


def fixture(path):
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE forecast_audit_runs(
            id INTEGER PRIMARY KEY,
            created_at INTEGER NOT NULL,
            country TEXT NOT NULL,
            item_name TEXT NOT NULL,
            source TEXT NOT NULL,
            status TEXT,
            active_prediction_number INTEGER
        )""")
        db.execute("""CREATE TABLE forecast_audit_points(
            id INTEGER PRIMARY KEY,
            run_id INTEGER NOT NULL,
            prediction_number INTEGER NOT NULL,
            estimate_timestamp INTEGER,
            window_end_timestamp INTEGER,
            recommended_arrival_timestamp INTEGER,
            recommended_leave_by_timestamp INTEGER,
            projected INTEGER,
            travel_reliability TEXT,
            model_name TEXT,
            projection_depth INTEGER
        )""")

        # First Nessie issue of hour: UI lower bound opens 840s after issue.
        rec = T0 + 7000
        win_end = T0 + 7200
        db.execute(
            "INSERT INTO forecast_audit_runs VALUES (?,?,?,?,?,?,?)",
            (1, T0, "uni", "Nessie Plushie", "live", "waiting_for_restock", 1),
        )
        db.execute(
            "INSERT INTO forecast_audit_points VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (1, 1, 1, T0 + 6900, win_end, rec, rec - UK, 0,
             "good", "old-v2", 0),
        )

        # Same item/hour later issue must not replace the frozen first issue.
        db.execute(
            "INSERT INTO forecast_audit_runs VALUES (?,?,?,?,?,?,?)",
            (2, T0 + 300, "uni", "Nessie Plushie", "live", "waiting_for_restock", 1),
        )
        db.execute(
            "INSERT INTO forecast_audit_points VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (2, 2, 1, T0 + 5000, T0 + 5200, T0 + 5100,
             T0 + 5100 - UK, 0, "excellent", "would-look-better-later", 0),
        )

        # Next hour has no active target; keep as an abstention.
        db.execute(
            "INSERT INTO forecast_audit_runs VALUES (?,?,?,?,?,?,?)",
            (3, T0 + 3600, "uni", "Nessie Plushie", "live",
             "no_reachable_forecast_within_horizon", None),
        )

        # Jaguar target requires >8h waiting and is excluded from current contract.
        mex_flight = m.TRAVEL_SECONDS["mex"]
        issue = T0
        late_arrival = issue + 9 * 3600 + mex_flight
        db.execute(
            "INSERT INTO forecast_audit_runs VALUES (?,?,?,?,?,?,?)",
            (4, issue, "mex", "Jaguar Plushie", "live",
             "using_future_reachable_cycle", 1),
        )
        db.execute(
            "INSERT INTO forecast_audit_points VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (4, 4, 1, late_arrival - 60, late_arrival, late_arrival - 120,
             late_arrival - 120 - mex_flight, 1, "marginal", "old-v2", 2),
        )
        db.commit()


class V136Tests(unittest.TestCase):
    def test_first_issue_ui_lower_bound_and_matched_leave_now(self):
        with tempfile.TemporaryDirectory() as tmp:
            dbp = Path(tmp) / "stock.db"
            fixture(dbp)

            ui_arrival = T0 + 7200
            stored_arrival = T0 + 7000
            now_arrival = T0 + UK
            calls = []

            def scorer(_db, country, item, arrival, asof):
                calls.append((country, item, arrival, asof))
                if arrival in (ui_arrival, stored_arrival):
                    return "POLL_STATE_PROXY_SUCCESS", True, {
                        "pre_quantity": 80, "post_quantity": 65
                    }
                if arrival == now_arrival:
                    return "POLL_STATE_PROXY_MISS", False, {
                        "pre_quantity": 0, "post_quantity": 0
                    }
                return "POLL_COVERAGE_TOO_SPARSE", None, {}

            out = m.audit(
                collector=dbp, asof=T0 + 50000, days=1, scorer=scorer
            )
            self.assertTrue(out["read_only"])
            self.assertEqual(
                out["status"], "V136_ORIGINAL_V2_STOCK_AT_ARRIVAL_BENCHMARK"
            )
            # Nessie hour 0, Nessie hour 1 abstention, Jaguar hour 0.
            self.assertEqual(out["first_issued_item_UTC_hourly_starts"], 3)

            s = out["overall"]
            self.assertEqual(s["valid_original_active_targets_under_8h_contract"], 1)
            self.assertEqual(s["no_active_target_or_invalid_current_contract"], 2)
            self.assertEqual(s["original_active_target_outside_current_8h_contract"], 1)
            self.assertEqual(s["matched_ui_vs_leave_now"], 1)
            self.assertEqual(s["matched_only_ui_stocked"], 1)
            self.assertEqual(s["matched_only_leave_now_stocked"], 0)
            self.assertEqual(s["ui_earliest_action_stock_at_least_30"], 1)
            self.assertEqual(s["leave_now_stock_below_30"], 1)
            self.assertAlmostEqual(s["ui_wait_minutes"]["median"], 14.0)

            example = out["recent_examples"][0]
            self.assertEqual(example["ui_action_departure_utc"], m.epoch_utc(T0 + 840))
            self.assertEqual(example["ui_action_arrival_utc"], m.epoch_utc(ui_arrival))
            self.assertEqual(example["ui_bracketing_quantities"], [80, 65])
            self.assertFalse(example["country_update_freshness_verified"])
            self.assertTrue(out["same_v88_poll_state_proxy_as_v75_v128"])
            self.assertEqual(len(out["per_item"]), 24)

            # The ignored second Nessie issue must never be scored.
            ignored_arrival = T0 + 5200
            self.assertFalse(any(call[2] == ignored_arrival for call in calls))

    def test_issue_time_when_lower_bound_already_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            dbp = Path(tmp) / "stock.db"
            with sqlite3.connect(dbp) as db:
                db.execute("""CREATE TABLE forecast_audit_runs(
                    id INTEGER PRIMARY KEY, created_at INTEGER, country TEXT,
                    item_name TEXT, source TEXT, status TEXT,
                    active_prediction_number INTEGER)""")
                db.execute("""CREATE TABLE forecast_audit_points(
                    id INTEGER PRIMARY KEY, run_id INTEGER,
                    prediction_number INTEGER, estimate_timestamp INTEGER,
                    window_end_timestamp INTEGER,
                    recommended_arrival_timestamp INTEGER,
                    recommended_leave_by_timestamp INTEGER, projected INTEGER,
                    travel_reliability TEXT, model_name TEXT,
                    projection_depth INTEGER)""")
                rec = T0 + UK - 300
                db.execute("INSERT INTO forecast_audit_runs VALUES (?,?,?,?,?,?,?)",
                           (1, T0, "uni", "Nessie Plushie", "live", "ok", 1))
                db.execute("INSERT INTO forecast_audit_points VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                           (1, 1, 1, rec, rec, rec, rec - UK, 0,
                            "good", "old-v2", 0))
                db.commit()

            arrivals = []
            def scorer(_db, _country, _item, arrival, _asof):
                arrivals.append(arrival)
                return "POLL_STATE_PROXY_SUCCESS", True, {}

            out = m.audit(
                collector=dbp, asof=T0 + 20000, days=1, scorer=scorer
            )
            ex = out["recent_examples"][0]
            self.assertEqual(ex["ui_wait_minutes"], 0.0)
            self.assertEqual(ex["ui_action_arrival_utc"], m.epoch_utc(T0 + UK))
            self.assertIn(T0 + UK, arrivals)

    def test_missing_tables_are_not_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            dbp = Path(tmp) / "stock.db"
            with sqlite3.connect(dbp) as db:
                db.execute("CREATE TABLE stock_history(dummy INTEGER)")
                db.commit()
            out = m.audit(collector=dbp, asof=T0, days=1)
            self.assertEqual(
                out["status"], "ORIGINAL_V2_FORECAST_AUDIT_TABLES_NOT_PRESENT"
            )
            with sqlite3.connect(dbp) as db:
                tables = {
                    r[0] for r in db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            self.assertEqual(tables, {"stock_history"})

    def test_bounded_run_count_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            dbp = Path(tmp) / "stock.db"
            fixture(dbp)
            with self.assertRaisesRegex(ValueError, "too many archived"):
                m.audit(
                    collector=dbp, asof=T0 + 50000,
                    days=1, limit=1, scorer=lambda *_: ("PENDING", None, {})
                )


if __name__ == "__main__":
    unittest.main()
