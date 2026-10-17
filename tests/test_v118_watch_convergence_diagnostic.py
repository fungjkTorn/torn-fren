"""V118 roll-forward vs stable restock target, source gaps, end-to-end CLI."""
import contextlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research import v118_watch_convergence_diagnostic as m

T0=1700000000
ITEM="uni:Nessie Plushie"


def record(issue,dep,*,item=ITEM,family="recent_phase_template",
           status="RESEARCH_PROPOSAL_ONLY"):
    return {
        "item_key":item,"computed_at":issue,
        "model_family":family,"model_config":"{}",
        "stock_as_of":issue,"status":status,
        "departure":dep,
        "arrival":dep+6360 if dep is not None else None,
        "valid_until":issue+300,"actual_player_departure":0,
    }


class ConvergenceAuditTests(unittest.TestCase):
    def test_rolling_target_constant_lead_never_becomes_executable(self):
        rows=[record(T0+i*300,T0+i*300+3600)
              for i in range(97)]
        times=[r["computed_at"] for r in rows]
        d=m.diagnose_start(rows[0],rows,times,asof=T0+30000)
        self.assertEqual(
            d["first_ready_status"],"NO_EXECUTABLE_DEPARTURE_WITHIN_8H")
        self.assertEqual(d["ready_valid_proposals"],0)
        self.assertEqual(d["watch_only_valid_proposals"],97)
        self.assertEqual(
            d["future_target_moves_one_for_one_with_tick_pairs"],96)
        self.assertEqual(
            d["future_target_stationary_within_one_minute_pairs"],0)
        self.assertEqual(
            d["original_departure_recheck"]["status"],
            "ORIGINAL_TARGET_SHIFTED_LATER")

    def test_fixed_target_becomes_actionable_before_issuance_expiration(self):
        rows=[
            record(T0+i*300,T0+1800)
            for i in range(7)
        ]
        times=[r["computed_at"] for r in rows]
        d=m.diagnose_start(rows[0],rows,times,asof=T0+30000)
        self.assertEqual(d["first_ready_status"],"EXECUTABLE_WITHIN_5M")
        self.assertEqual(d["first_ready_epoch"],T0+1800)
        self.assertEqual(d["ready_valid_proposals"],2)
        self.assertEqual(d["future_target_stationary_within_one_minute_pairs"],6)
        self.assertEqual(
            d["original_departure_recheck"]["status"],
            "ORIGINAL_TARGET_RECONFIRMED_ACTIONABLE")

    def test_sparse_ticks_not_conflated_with_rolling_forecasts(self):
        rows=[
            record(T0,T0+3600),
            record(T0+3000,T0+6600),
            record(T0+6000,T0+9600),
        ]
        d=m.diagnose_start(
            rows[0],rows,[r["computed_at"] for r in rows],
            asof=T0+30000)
        self.assertEqual(d["tick_gaps_over_10_minutes"],2)
        self.assertEqual(d["all_stored_ticks"],3)
        self.assertEqual(d["valid_adjacent_departure_drift_pairs"],0)
        self.assertEqual(d["first_ready_status"],
                         "NO_EXECUTABLE_DEPARTURE_WITHIN_8H")

    def test_pending_target_is_not_scored_as_rolled_or_failed(self):
        rows=[record(T0,T0+3600),record(T0+300,T0+3900)]
        result=m.target_recheck(rows[0],rows,
                                [r["computed_at"] for r in rows],
                                asof=T0+600)
        self.assertEqual(result["status"],"ORIGINAL_TARGET_NOT_MATURE")

    def test_cli_full_text_and_json_with_readonly_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            dbpath=Path(tmp)/"research.sqlite"
            with sqlite3.connect(dbpath) as db:
                db.execute("""CREATE TABLE v42_candidate_decisions(
                    id INTEGER PRIMARY KEY,item_key TEXT,
                    computed_at INTEGER,model_family TEXT,model_config TEXT,
                    stock_as_of INTEGER,status TEXT,departure INTEGER,
                    arrival INTEGER,valid_until INTEGER,
                    actual_player_departure INTEGER
                )""")
                db.executemany("""INSERT INTO v42_candidate_decisions(
                    item_key,computed_at,model_family,model_config,stock_as_of,
                    status,departure,arrival,valid_until,
                    actual_player_departure)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    [tuple(row[k] for k in (
                        "item_key","computed_at","model_family",
                        "model_config","stock_as_of","status",
                        "departure","arrival","valid_until",
                        "actual_player_departure"))
                    for row in (
                        record(T0,T0+3600),
                        record(T0+300,T0+3900),
                        record(T0+600,T0+4200),
                    )])
                db.commit()
            r=m.audit(ledger=dbpath,now=T0+30000,
                      hours=12,keys=(ITEM,))
            self.assertEqual(r["hourly_starts"],1)
            self.assertEqual(r["per_item"][ITEM]["starts"],1)
            self.assertEqual(r["overall"]["no_ready_proposals"],1)
            self.assertEqual(r["overall"]["rolling_one_for_one_pairs"],2)
            self.assertTrue(r["read_only"])
            real=m.audit
            with (patch.object(m,"audit",
                               side_effect=lambda **kw:real(
                                   ledger=dbpath,now=T0+30000,**kw)),
                  patch.object(m,"approved_collector_source",
                               return_value=True)):
                for json_mode in (False,True):
                    argv=["v118","--hours","12",
                          "--items","nessie"]
                    if json_mode:argv.append("--json")
                    output=io.StringIO()
                    with (patch.object(sys,"argv",argv),
                          contextlib.redirect_stdout(output)):
                        m.main()
                    if json_mode:
                        rep=json.loads(output.getvalue())
                        self.assertEqual(rep["status"],
                            "V118_FIVE_MINUTE_WATCH_CONVERGENCE_AND_TICK_COVERAGE")
                        self.assertEqual(rep["hourly_starts"],1)
                    else:
                        self.assertIn("WHY FUTURE WATCHES NEVER CONVERGE",
                                      output.getvalue())


if __name__=="__main__":
    unittest.main()
