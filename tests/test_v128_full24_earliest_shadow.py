"""V128 24 roster, country timing, asof, closed source, no-write, UK parity."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research import v128_full24_earliest_shadow as m
from research import v125_earliest_credible_shadow as uk
from research.v107_explicit_restock_cycle_baseline import (
    StockObservation,completed_phases,
)

T0=1790000000


def trace(*,cycles=22,phase="HIGH",with_switch=False):
    t=T0
    result=[StockObservation(t,0,"yata")]
    for i in range(cycles):
        t+=7200
        result.append(StockObservation(t,300,"yata"))
        if phase=="HIGH" and i==cycles-1:
            break
        t+=3600
        result.append(StockObservation(t,0,"yata"))
    if with_switch:
        t+=100
        result.append(StockObservation(t,100,"prometheus"))
    return result,t


def collector_fixture(path,roster):
    trace_rows,last=trace(cycles=22,phase="HIGH")
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE stock_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER,quantity INTEGER,source TEXT,
            country TEXT,item_name TEXT
        )""")
        conn.execute("""CREATE TABLE poll_heartbeats(
            timestamp INTEGER,source TEXT,mode TEXT,success INTEGER
        )""")
        conn.execute("""CREATE TABLE collection_gaps(
            start_timestamp INTEGER,end_timestamp INTEGER
        )""")
        for key in roster:
            country,item=key.split(":",1)
            conn.executemany("""INSERT INTO stock_history(
                timestamp,quantity,source,country,item_name
            ) VALUES (?,?,?,?,?)""",[
                (x.epoch,x.quantity,x.source,country,item)
                for x in trace_rows
            ])
        conn.execute("""INSERT INTO poll_heartbeats(
            timestamp,source,mode,success
        ) VALUES (?,'yata','poll-cycle',1)""",(last+20,))
        conn.commit()
    return last+20


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Full24ShadowTests(unittest.TestCase):
    def test_exact_roster_adds_both_missing_generic_xanax_not_unlisted(self):
        roster=m.exact_roster()
        self.assertEqual(len(roster),24)
        self.assertEqual(len(set(roster)),24)
        self.assertEqual(roster["can:Xanax"]["incumbent_model_config"],"dyn8")
        self.assertEqual(roster["uni:Xanax"]["incumbent_model_config"],"dyn3")
        self.assertTrue(roster["jap:Xanax"]["incumbent_preview_only"])
        self.assertTrue(roster["chi:Panda Plushie"]["incumbent_preview_only"])
        self.assertTrue(roster["sou:Lion Plushie"]["incumbent_preview_only"])
        self.assertTrue(all(k.split(":",1)[0] in m.TRAVEL_SECONDS for k in roster))

    def test_roster_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as t:
            f=Path(t)/"manifest.json"
            raw=json.loads(m.ROSTER.read_text())
            raw["items"].pop("uni:Nessie Plushie")
            f.write_text(json.dumps(raw))
            with self.assertRaises(ValueError):
                m.exact_roster(f)

    def test_fast_completed_phase_equivalence_with_old_extractor(self):
        rows,_=trace(cycles=21,phase="LOW")
        gaps=[(T0+15000,T0+15500),(T0+25000,T0+25800)]
        expected=completed_phases(
            rows,asof=rows[-1].epoch,collection_gaps=gaps)
        out=m.fast_phases(rows,asof=rows[-1].epoch,gaps=gaps)
        for field in ("phase","phase_onset","stocked_durations",
                      "depleted_durations","last_observation"):
            self.assertEqual(out[field],expected[field],field)
        with self.assertRaisesRegex(ValueError,"future item"):
            m.fast_phases(rows,asof=T0-1,gaps=gaps)

    def test_uk_scores_match_existing_v125_at_exact_asof(self):
        rows,t=trace(cycles=22,phase="HIGH")
        old=uk.phase_survival_curve(
            rows,"uni:Nessie Plushie",asof=t+20,scenarios=128)
        self.assertEqual(old["status"],"ISSUED_TWO_PHASE_SCENARIO_CURVE")
        new=m.empirical_arrival_scores(
            m.fast_phases(rows,asof=t+20),
            "uni:Nessie Plushie",asof=t+20)
        self.assertEqual(new["scores"],old["scores"])
        self.assertEqual(
            new["earliest_immediate_arrival_score"],
            old["score_at_immediate_departure"])
        ours=m.earliest_credible_for_country(new,"uni:Nessie Plushie")
        orig=uk.earliest_credible(old)
        self.assertEqual(ours["departure"],orig["departure"])
        self.assertEqual(ours["arrival"],orig["arrival"])

    def test_per_country_flight_duration_and_earliest_gate(self):
        rows,at=trace()
        for key in ("mex:Jaguar Plushie","jap:Xanax",
                    "sou:Lion Plushie","uni:Red Fox Plushie"):
            model=m.empirical_arrival_scores(
                m.fast_phases(rows,asof=at),key,asof=at)
            result=m.earliest_credible_for_country(model,key)
            self.assertEqual(model["status"],
                             "ISSUED_EMPIRICAL_TWO_PHASE_CURVE")
            if result["departure"] is not None:
                self.assertEqual(result["arrival"]-result["departure"],
                                 m.TRAVEL_SECONDS[key.split(":",1)[0]])
                self.assertTrue(at<=result["departure"]<=at+m.MAX_WAIT)
        self.assertNotEqual(
            m.TRAVEL_SECONDS["mex"],m.TRAVEL_SECONDS["sou"])

    def test_no_false_phase_onset_on_switch(self):
        rows,t=trace(with_switch=True)
        curve=m.empirical_arrival_scores(
            m.fast_phases(rows,asof=t+20),
            "uni:Nessie Plushie",asof=t+20)
        self.assertEqual(curve["status"],"CURRENT_PHASE_ONSET_UNKNOWN")
        self.assertIsNone(curve["phase_onset"])

    def test_preview_has_24_rows_no_source_or_sidecar_changes(self):
        with tempfile.TemporaryDirectory() as t:
            src=Path(t)/"collector.db"
            dst=Path(t)/"shadow.db"
            now=collector_fixture(src,m.exact_roster())
            before=digest(src)
            result=m.observe(source=src,sidecar=dst,issued=now,
                             clock=lambda:now,canonical=False)
            self.assertEqual(result["status"],"V128_PREVIEW_24_NO_WRITES")
            self.assertEqual(result["roster_count"],24)
            self.assertEqual(set(result["predictions"]),set(m.exact_roster()))
            self.assertTrue(result["all_24_keys_recorded_including_abstentions"])
            self.assertFalse(dst.exists())
            self.assertEqual(before,digest(src))
            for key,row in result["predictions"].items():
                self.assertEqual(row["travel_seconds"],
                    m.TRAVEL_SECONDS[key.split(":",1)[0]])
                self.assertEqual(row["baseline_leave_now_arrival"]-now,
                    m.TRAVEL_SECONDS[key.split(":",1)[0]])
                self.assertFalse(row["published_to_website"])
                self.assertFalse(row["collector_country_freshness_verified"])

    def test_record_all_24_and_deduplicate_repeat_tick(self):
        with tempfile.TemporaryDirectory() as t:
            src=Path(t)/"collector.db"
            dst=Path(t)/"shadow.db"
            now=collector_fixture(src,m.exact_roster())
            digest_before=digest(src)
            a=m.observe(source=src,sidecar=dst,issued=now,
                        clock=lambda:now,canonical=False,record=True)
            self.assertEqual(a["status"],"V128_RECORDED_24_PRIVATE")
            m.observe(source=src,sidecar=dst,issued=now,
                      clock=lambda:now,canonical=False,record=True)
            with sqlite3.connect(dst) as conn:
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM v128_ticks").fetchone()[0],1)
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM v128_issued").fetchone()[0],24)
                keys=[x[0] for x in conn.execute(
                    "SELECT item_key FROM v128_issued")]
                self.assertEqual(set(keys),set(m.exact_roster()))
            self.assertEqual(digest_before,digest(src))

    def test_stale_heartbeat_records_24_explicit_abstentions(self):
        with tempfile.TemporaryDirectory() as t:
            src=Path(t)/"collector.db"
            dst=Path(t)/"shadow.db"
            now=collector_fixture(src,m.exact_roster())
            out=m.observe(source=src,sidecar=dst,issued=now+900,
                          clock=lambda:now+900,canonical=False)
            self.assertEqual(out["roster_count"],24)
            self.assertEqual(
                out["decision_status_counts"]["ABSTAIN_GLOBAL_HEARTBEAT_STALE"],
                24)
            self.assertFalse(dst.exists())

    def test_budget_skips_remaining_work_without_overstating_coverage(self):
        with tempfile.TemporaryDirectory() as t:
            src=Path(t)/"collector.db"
            dst=Path(t)/"shadow.db"
            now=collector_fixture(src,m.exact_roster())
            out=m.observe(source=src,sidecar=dst,issued=now,
                          clock=lambda:now,canonical=False,budget_seconds=-1)
            self.assertEqual(
                out["decision_status_counts"]["ABSTAIN_RESOURCE_BUDGET"],24)

    def test_roster_source_collector_must_not_be_destination(self):
        with tempfile.TemporaryDirectory() as t:
            src=Path(t)/"collector.db"
            collector_fixture(src,m.exact_roster())
            with self.assertRaises(ValueError):
                m.safe_paths(src,src,canonical=False)


if __name__=="__main__":
    unittest.main()
