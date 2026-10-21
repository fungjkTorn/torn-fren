"""Synthetic prospective issue and independent evidence checks."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research.physical_event_forward import freeze, record, score


SHA = "a" * 40
ISSUED = 1000


def snapshot():
    items = {}
    for i in range(24):
        key = f"mex:Item {i}"
        forecast = dict(item_key=key, asof_epoch=ISSUED, flight_seconds=300,
                        status="EVENT_TIMELINE_FORECAST_AVAILABLE",
                        model_name="physical_restock_test",
                        true_restock_events=[], restock_events=[],
                        current_stock_window=None)
        if i == 0:
            forecast["true_restock_events"] = [
                dict(predicted_restock_epoch=1200, restock_early_epoch=1190,
                     restock_late_epoch=1210),
                dict(predicted_restock_epoch=1700, restock_early_epoch=1690,
                     restock_late_epoch=1710)]
            forecast["restock_events"] = [
                dict(predicted_restock_epoch=1200,
                     predicted_stock_below_30_epoch=1250,
                     early_stock_end_epoch=1240),
                dict(predicted_restock_epoch=1700,
                     predicted_stock_below_30_epoch=2300,
                     early_stock_end_epoch=2200)]
        items[key] = forecast
    return dict(asof_epoch=ISSUED, model_sha=SHA, items=items,
                source_heartbeat_age_seconds=5,
                production_model_promoted=False)


def collector(path, switch=False, gap=False):
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE stock_history (
            id INTEGER PRIMARY KEY, country TEXT, item_name TEXT,
            timestamp INTEGER, quantity INTEGER, source TEXT)""")
        db.execute("""CREATE TABLE poll_heartbeats (
            id INTEGER PRIMARY KEY, mode TEXT, success INTEGER,
            timestamp INTEGER, source TEXT)""")
        db.execute("""CREATE TABLE collection_gaps (
            start_timestamp INTEGER, end_timestamp INTEGER)""")
        for t, q in ((900, 0), (1200, 50), (1300, 0), (1700, 50), (2100, 0)):
            db.execute("INSERT INTO stock_history(country,item_name,timestamp,quantity,source) VALUES(?,?,?,?,?)",
                       ("mex", "Item 0", t, q, "provider-a"))
        for t in range(900, 2700, 100):
            source = "provider-b" if switch and t == 1500 else "provider-a"
            db.execute("INSERT INTO poll_heartbeats(mode,success,timestamp,source) VALUES(?,?,?,?)",
                       ("poll-cycle", 1, t, source))
        if gap:
            db.execute("INSERT INTO collection_gaps VALUES (?,?)", (1450, 1550))


class ProspectiveEventTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.ledger = root / "physical_event_forward.db"
        self.stock = root / "sanitized_collector.db"

    def test_physical_ordinal_two_selected_after_first_unreachable(self):
        b = freeze(snapshot())
        self.assertEqual(len(b["rows"]), 24)
        r = b["rows"]["mex:Item 0"]
        self.assertEqual([e["index"] for e in r["physical_events"]], [1, 2])
        self.assertFalse(r["physical_events"][0]["flight_reachable"])
        self.assertTrue(r["physical_events"][1]["flight_reachable"])
        self.assertEqual(r["selected_event_index"], 2)
        self.assertEqual(r["departure_epoch"], 1400)
        self.assertEqual(r["arrival_epoch"], 1700)
        self.assertEqual(r["arrival_plus_10_epoch"], 1710)
        self.assertEqual(r["departure_deadline_epoch"], 1989)
        self.assertEqual(r["decision_status"], "WAIT_FOR_ESTIMATED_DEPARTURE")

    def test_append_only_and_matched_second_event(self):
        batch = freeze(snapshot())
        record(batch, self.ledger)
        collector(self.stock)
        report = score(sidecar=self.ledger, collector=self.stock, now=2600)
        r = report["per_item"]["mex:Item 0"]
        self.assertEqual(report["issued_item_rows"], 24)
        self.assertEqual(report["first_issued_item_hours"], 24)
        self.assertEqual(r["first_physical_resolved"], 1)
        self.assertEqual(r["distinct_first_physical_restocks"], 1)
        self.assertEqual(r["distinct_restock_possible_within_15s"], 1)
        self.assertEqual(r["chosen_physical_resolved"], 1)
        self.assertEqual(r["restock_possible_within_15s"], 1)
        self.assertNotIn("restock_certain_within_15s", r)
        self.assertEqual(r["future_departure_requires_reconfirmation"], 1)
        self.assertEqual(r["landing_proxy_hit"], 1)
        self.assertEqual(r["requires_reconfirmation_landing_hit"], 1)
        self.assertEqual(r["distinct_target_arrival_known"], 1)
        self.assertEqual(r["distinct_target_arrival_hit"], 1)
        self.assertEqual(r["matched_leave_now_pairs"], 1)
        self.assertEqual(r["matched_recommendation_hits"], 1)
        self.assertEqual(r["matched_leave_now_hits"], 0)
        with self.assertRaises(sqlite3.IntegrityError):
            record(batch, self.ledger)

    def test_provider_switch_or_gap_is_not_false_certainty(self):
        record(freeze(snapshot()), self.ledger)
        collector(self.stock, switch=True)
        report = score(sidecar=self.ledger, collector=self.stock, now=2600)
        row = report["per_item"]["mex:Item 0"]
        self.assertEqual(row["chosen_physical_unknown"], 1)
        self.assertNotIn("chosen_physical_resolved", row)

    def test_untrusted_or_stale_issue_rejected(self):
        s = snapshot()
        s["source_heartbeat_age_seconds"] = 181
        with self.assertRaises(ValueError):
            freeze(s)
        s = snapshot()
        s["items"]["mex:Item 0"]["asof_epoch"] += 1
        with self.assertRaises(ValueError):
            freeze(s)
        s = snapshot()
        s["items"].pop("mex:Item 23")
        with self.assertRaises(ValueError):
            freeze(s)

    def test_publication_is_actual_issue_not_slow_forecast_start(self):
        b = freeze(snapshot(), published_epoch=1010)
        self.assertEqual(b["issued_epoch"], 1010)
        self.assertEqual(b["forecast_asof_epoch"], 1000)
        row = b["rows"]["mex:Item 0"]
        self.assertEqual(row["issued_epoch"], 1010)
        self.assertEqual(row["source_poll_age_seconds"], 15)
        self.assertEqual(row["issue_latency_seconds"], 10)
        self.assertEqual(row["departure_epoch"], 1400)
        with self.assertRaises(ValueError):
            freeze(snapshot(), published_epoch=1200)
        with self.assertRaises(ValueError):
            freeze(snapshot(), published_epoch=999)

    def test_real_24_item_fixture_roundtrip(self):
        from research.build_travel_event_snapshot import prepare
        import test_continuous_departure_replay as fixtures
        with tempfile.TemporaryDirectory() as folder:
            db = fixtures.ContinuousTests().fixture(Path(folder))
            s = prepare(db, model_sha=SHA, now=fixtures.T)
            b = freeze(s, published_epoch=fixtures.T + 10)
            self.assertEqual(len(b["rows"]), 24)

    def test_read_only_collector_separation(self):
        record(freeze(snapshot()), self.ledger)
        with self.assertRaises(ValueError):
            score(sidecar=self.ledger, collector=self.ledger)
        with self.assertRaises(ValueError):
            score(sidecar=self.ledger, collector=self.stock, days=20)


if __name__ == "__main__":
    unittest.main()
