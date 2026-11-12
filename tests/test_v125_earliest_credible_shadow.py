"""V125: earliest supported flight, HIGH+LOW states, safely preserved issues."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research import v125_earliest_credible_shadow as m
from research.v107_explicit_restock_cycle_baseline import StockObservation

T0=1700000000
ITEM="uni:Nessie Plushie"


def obs_last(*,cycles=20,phase="LOW",age=0):
    t=T0
    obs=[StockObservation(t,0,"yata")]
    for i in range(cycles):
        t+=7200
        obs.append(StockObservation(t,200,"yata"))
        if phase=="HIGH" and i==cycles-1:
            break
        t+=3600
        obs.append(StockObservation(t,0,"yata"))
    return obs,t+age


def fixture_db(path,phase="LOW"):
    last,t=obs_last(phase=phase,age=100)
    with sqlite3.connect(path) as con:
        con.execute("""CREATE TABLE stock_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER,quantity INTEGER,source TEXT,
            country TEXT,item_name TEXT
        )""")
        con.execute("""CREATE TABLE poll_heartbeats (
            timestamp INTEGER,source TEXT,mode TEXT,success INTEGER
        )""")
        con.execute("""CREATE TABLE collection_gaps (
            start_timestamp INTEGER,end_timestamp INTEGER
        )""")
        for _,item in m.TARGETS.values():
            con.executemany("""INSERT INTO stock_history(
                timestamp,quantity,source,country,item_name)
                VALUES (?,?,?,'uni',?)""",[
                    (o.epoch,o.quantity,o.source,item) for o in last
                ])
        con.execute("""INSERT INTO poll_heartbeats(
            timestamp,source,mode,success)
            VALUES (?,'yata','poll-cycle',1)""",(t,))
        con.commit()
    return t


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class EarliestCredibleTests(unittest.TestCase):
    def test_low_state_earliest_positive_after_short_wait(self):
        rows,at=obs_last()
        curve=m.phase_survival_curve(rows,ITEM,asof=at,scenarios=64)
        self.assertEqual(curve["status"],"ISSUED_TWO_PHASE_SCENARIO_CURVE")
        self.assertEqual(curve["observed_current_phase"],"LOW")
        self.assertEqual(curve["score_at_immediate_departure"],0.0)
        decision=m.earliest_credible(curve)
        self.assertEqual(decision["status"],"EARLIEST_WAIT_SUPPORTED")
        self.assertEqual(decision["departure"],at+900)
        self.assertEqual(decision["arrival"],at+900+6360)
        self.assertGreaterEqual(decision["score"],.60)

    def test_current_stocked_state_needs_delay_when_flight_lands_depleted(self):
        rows,at=obs_last(phase="HIGH")
        curve=m.phase_survival_curve(rows,ITEM,asof=at,scenarios=64)
        self.assertEqual(curve["observed_current_phase"],"HIGH")
        self.assertEqual(curve["score_at_immediate_departure"],0.0)
        decision=m.earliest_credible(curve)
        self.assertEqual(decision["status"],"EARLIEST_WAIT_SUPPORTED")
        self.assertGreater(decision["departure"],at)
        self.assertLessEqual(decision["departure"],at+28800)

    def test_now_is_earliest_when_matured_stock_timeline_supports_it(self):
        curve={
            "status":"ISSUED_TWO_PHASE_SCENARIO_CURVE",
            "asof_epoch":T0,
            "delay_seconds":[0,300,600,900],
            "scores":[.8,.7,.95,1.0],
        }
        decision=m.earliest_credible(curve)
        self.assertEqual(decision["departure"],T0)
        self.assertEqual(decision["status"],"EARLIEST_NOW")
        curve["scores"]=[.4,.7,.7,.95]
        self.assertEqual(m.earliest_credible(curve)["departure"],T0+300)
        curve["scores"]=[.4,.7,.3,.85]
        self.assertIsNone(m.earliest_credible(curve)["departure"])

    def test_one_high_bin_not_sufficient_for_two_consecutive_gate(self):
        curve={
            "status":"ISSUED_TWO_PHASE_SCENARIO_CURVE",
            "asof_epoch":T0,
            "delay_seconds":[0,300,600,900],
            "scores":[1.0,.0,.9,.1],
        }
        self.assertEqual(m.earliest_credible(curve)["status"],
                         "NO_QUALIFYING_DEPARTURE_IN_EIGHT_HOURS")

    def test_past_only_and_old_change_explicit_abstention(self):
        rows,at=obs_last()
        with self.assertRaisesRegex(ValueError,"future"):
            m.phase_survival_curve(rows,ITEM,asof=at-1)
        stale=m.phase_survival_curve(
            rows,ITEM,asof=at+7*3600,scenarios=64)
        self.assertEqual(stale["status"],"ITEM_CHANGE_OBSERVATION_TOO_OLD")
        very_few,earlier=obs_last(cycles=2)
        self.assertEqual(m.phase_survival_curve(
            very_few,ITEM,asof=earlier,scenarios=64)["status"],
            "INSUFFICIENT_COMPLETED_PHASES")

    def test_preview_default_is_no_write_and_phase_is_correct(self):
        with tempfile.TemporaryDirectory() as tmp:
            stock=Path(tmp)/"collector.db"
            side=Path(tmp)/"v125.db"
            now=fixture_db(stock)
            before=sha(stock)
            output=m.observe(source=stock,sidecar=side,now=now,
                             record=False,enforce=False)
            self.assertEqual(output["status"],"V125_PREVIEW_NO_WRITES")
            self.assertEqual(before,sha(stock))
            self.assertFalse(side.exists())
            self.assertEqual(len(output["as_issued_model_recommendations"]),2)
            for r in output["as_issued_model_recommendations"].values():
                self.assertEqual(r["phase"],"LOW")
                self.assertEqual(r["status"],"ISSUED_TWO_PHASE_SCENARIO_CURVE")
                self.assertEqual(
                    r["decision_status"],"EARLIEST_WAIT_SUPPORTED")
                self.assertFalse(r["country_provider_freshness_verified"])
                self.assertGreater(r["earliest_departure"],now)

    def test_explicit_record_is_idempotent_and_records_all_five_minute_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            stock=Path(tmp)/"collector.db"
            side=Path(tmp)/"v125.db"
            now=fixture_db(stock)
            original=sha(stock)
            m.observe(source=stock,sidecar=side,now=now,
                      record=True,enforce=False)
            m.observe(source=stock,sidecar=side,now=now,
                      record=True,enforce=False)
            with sqlite3.connect(stock) as con:
                con.execute("""INSERT INTO poll_heartbeats(
                    timestamp,source,mode,success)
                    VALUES (?,'yata','poll-cycle',1)""",(now+300,))
                con.commit()
            m.observe(source=stock,sidecar=side,now=now+300,
                      record=True,enforce=False)
            with sqlite3.connect(side) as con:
                self.assertEqual(con.execute(
                    "SELECT count(*) FROM v125_issued").fetchone()[0],4)
                epochs=[x[0] for x in con.execute(
                    "SELECT DISTINCT issued_epoch FROM v125_issued ORDER BY 1")]
                self.assertEqual(epochs,[now,now+300])
                content=json.loads(con.execute(
                    "SELECT payload_json FROM v125_issued LIMIT 1"
                ).fetchone()[0])
                self.assertEqual(content["policy_id"],m.POLICY_ID)
            self.assertNotEqual(sha(stock),original)
            # Only the TEST inserted heartbeat; V125 itself did not alter the
            # source. Read-only preview must remain no-write.
            before=sha(stock)
            m.observe(source=stock,sidecar=side,now=now+300,
                      record=False,enforce=False)
            self.assertEqual(sha(stock),before)

    def test_canonical_private_path_and_fresh_heartbeat_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            stock=Path(tmp)/"stock.db"
            side=Path(tmp)/"side.db"
            now=fixture_db(stock)
            with self.assertRaises(ValueError):
                m.canonical_paths(source=stock,sidecar=side,enforce=True)
            output=m.observe(source=stock,sidecar=side,now=now+1000,
                             enforce=False)
            self.assertEqual(output["global_heartbeat_age_seconds"],1000)
            self.assertFalse(side.exists())
            for r in output["as_issued_model_recommendations"].values():
                self.assertEqual(r["status"],"GLOBAL_HEARTBEAT_STALE")

    def test_phase_onset_not_mislabeled_depletion_for_high(self):
        rows,issued=obs_last(phase="HIGH",age=30)
        record=m.issued_research_record(ITEM,rows,[],issued=issued)
        self.assertEqual(record["phase"],"HIGH")
        self.assertEqual(record["phase_onset"],rows[-1].epoch)
        self.assertIn("earliest_departure",record)
        self.assertEqual(record["baseline_leave_now_arrival"],issued+6360)


if __name__=="__main__":
    unittest.main()
