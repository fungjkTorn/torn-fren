"""V87 contract tests: 21 originals unchanged, three private previews inert."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research import v87_experimental24_overlay as m
from research.v81_pair_forward_comparison import SCHEMA as PAIR_SCHEMA
from research.v84_japan_forward_canary import SCHEMA as JAPAN_SCHEMA

NOW = 1791686190


class OverlayTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.pair = root / "pairs.db"
        self.japan = root / "japan.db"
        with sqlite3.connect(self.pair) as c:
            c.execute(PAIR_SCHEMA)
        with sqlite3.connect(self.japan) as c:
            c.execute(JAPAN_SCHEMA)
        self.original = {
            "source": "v75-private21", "experimental": True,
            "prediction_accuracy_verified": False,
            "latest": [{"item_key": f"original:{i}", "marker": i}
                       for i in range(21)]}

    def pair_add(self, key, *, status="FORWARD_CANDIDATE_ONLY",
                 dep=NOW + 1200, issued=NOW-30, variant="selector",
                 source_lag=20):
        travel = m.TRAVEL[key]
        with sqlite3.connect(self.pair) as c:
            c.execute("""INSERT INTO pair_issued_decisions(
                item_key,variant,issued_at,planned_at,stock_as_of,
                valid_until,status,selected_expert,departure,arrival,
                artifact_sha256,min_quantity,grace_seconds,actual_player_departure)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (key, variant, issued, issued//300*300, issued-source_lag,
                 issued+300, status, "a", dep if status=="FORWARD_CANDIDATE_ONLY" else None,
                 dep+travel if status=="FORWARD_CANDIDATE_ONLY" else None,
                 m.PINS[key], 30, 10, 0))

    def japan_add(self, *, status="FORWARD_CANDIDATE_ONLY",
                  dep=NOW+1500, issued=NOW-25, hb_lag=25):
        with sqlite3.connect(self.japan) as c:
            c.execute("""INSERT INTO japan_forward_decisions(
                slot,queried_at,issued_at,source_heartbeat,
                status,model_generation,model_config,departure,arrival,
                quantity_threshold,grace_seconds,actual_player_departure,
                source_model,experiment) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (issued//300*300, issued-8, issued, issued-hb_lag,
                 status, "V8_REGIME_CANDIDATE", "V7_ordinary_regime",
                 dep if status=="FORWARD_CANDIDATE_ONLY" else None,
                 dep+8940 if status=="FORWARD_CANDIDATE_ONLY" else None,
                 30, 10, 0, "v8_regime_candidate_checkpoint_parity_pending",
                 "v84_japan_private_canary"))

    def merge(self, *, now=NOW):
        return m.merge_response(self.original, now=now,
                                pair_db=self.pair, japan_db=self.japan)

    def test_roster_exactly_24_without_modifying_first_21(self):
        self.pair_add("chi:Panda Plushie")
        self.pair_add("sou:Lion Plushie")
        self.japan_add()
        out = self.merge()
        self.assertEqual(len(out["latest"]), 24)
        self.assertEqual(out["latest"][:21], self.original["latest"])
        self.assertEqual(len(self.original["latest"]), 21)
        self.assertEqual([r["item_key"] for r in out["latest"][21:]], list(m.ADDED))
        self.assertFalse(out["prediction_accuracy_verified"])
        self.assertTrue(all(r["experimental"] and not r["actionable"] and
                            not r["prediction_accuracy_verified"]
                            for r in out["latest"][21:]))
        self.assertTrue(all(r["status"] == "RESEARCH_PREVIEW_UNVALIDATED"
                            for r in out["latest"][21:]))

    def test_missing_sidecars_show_three_explicit_no_result_rows(self):
        out = m.merge_response(self.original, now=NOW, pair_db=self.pair.parent/"bad.db",
                               japan_db=self.japan.parent/"missing.db")
        self.assertEqual(len(out["latest"]), 24)
        self.assertTrue(all(r["departure"] is None and r["arrival"] is None
                            for r in out["latest"][21:]))

    def test_expired_departure_never_actionable(self):
        self.pair_add("sou:Lion Plushie", dep=NOW-5)
        self.japan_add(dep=NOW-5)
        out = self.merge()
        for row in out["latest"][21:]:
            self.assertFalse(row["actionable"])
            self.assertTrue(row["departure"] is None)

    def test_stale_pair_does_not_recycle_older_candidate(self):
        self.pair_add("chi:Panda Plushie", issued=NOW-480)
        out = self.merge()
        row = out["latest"][21]
        self.assertEqual(row["status"], "RESEARCH_PREVIEW_STALE")
        self.assertIsNone(row["departure"])

    def test_latest_abstention_overrides_previous_candidate(self):
        self.pair_add("chi:Panda Plushie", issued=NOW-120)
        self.pair_add("chi:Panda Plushie", status="EXPERT_ABSTAINED", issued=NOW-20)
        out = self.merge()
        row = out["latest"][21]
        self.assertEqual(row["status"], "RESEARCH_PREVIEW_EXPERT_ABSTAINED")
        self.assertIsNone(row["departure"])

    def test_selected_preview_returns_only_requested_item(self):
        self.japan_add()
        source = {**self.original, "latest": []}
        out = m.overlay_response(source, key="jap:Xanax", now=NOW,
                                 pair_db=self.pair, japan_db=self.japan)
        self.assertEqual(len(out["latest"]), 1)
        self.assertEqual(out["latest"][0]["item_key"], "jap:Xanax")
        self.assertFalse(out["latest"][0]["actionable"])
        self.assertFalse(out["latest"][0]["prediction_accuracy_verified"])

    def test_legacy_filtered_response_remains_unchanged(self):
        original = {**self.original, "latest": [self.original["latest"][3]]}
        result = m.overlay_response(original, key="arg:Monkey Plushie", now=NOW,
                                    pair_db=self.pair, japan_db=self.japan)
        self.assertEqual(result, original)

    def test_base_roster_drift_preserves_original_response(self):
        original = {**self.original, "latest": self.original["latest"][:20]}
        result = m.overlay_response(original, now=NOW,
                                    pair_db=self.pair, japan_db=self.japan)
        self.assertEqual(result["latest"], original["latest"])
        self.assertEqual(result["preview_overlay_status"], "BASE_ROSTER_NOT_21")

    def test_reject_non_21_or_colliding_roster(self):
        for rows in ([], [{"item_key":"x"}]*21,
                     [{"item_key":"jap:Xanax"}]+self.original["latest"][1:]):
            with self.assertRaises(ValueError):
                m.merge_response({**self.original, "latest":rows},
                                 now=NOW, pair_db=self.pair, japan_db=self.japan)

    def test_bad_pair_timing_fails_closed(self):
        self.pair_add("chi:Panda Plushie", source_lag=190)
        out = self.merge()
        self.assertIsNone(out["latest"][21]["departure"])
        self.assertEqual(out["latest"][21]["status"], "RESEARCH_PREVIEW_STALE")

    def test_wrong_pair_artifact_rejected(self):
        self.pair_add("chi:Panda Plushie")
        with sqlite3.connect(self.pair) as con:
            con.execute("UPDATE pair_issued_decisions SET artifact_sha256=?",
                        ("wrong-artifact",))
        row = self.merge()["latest"][21]
        self.assertEqual(row["status"], "RESEARCH_PREVIEW_INVALID")
        self.assertIsNone(row["departure"])

    def test_japan_invalid_nonfresh_fails_closed(self):
        self.japan_add(hb_lag=200)
        out = self.merge()
        self.assertIsNone(out["latest"][23]["departure"])
        self.assertEqual(out["latest"][23]["status"],
                         "RESEARCH_PREVIEW_STALE_OR_INVALID")


if __name__ == "__main__":
    unittest.main()
