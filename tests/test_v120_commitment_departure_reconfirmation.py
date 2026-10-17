"""V120 frozen V119 commitments audited without changing policy selection."""
import contextlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research import v120_commitment_departure_reconfirmation as m

T0=1700000000
ITEM="uni:Nessie Plushie"


def candidate(at,dep,*,status="RESEARCH_PROPOSAL_ONLY"):
    return {
        "item_key":ITEM,
        "computed_at":at,
        "stock_as_of":at,
        "status":status,
        "valid_until":at+300,
        "model_family":"recent_phase_template",
        "model_config":"test",
        "departure":dep,
        "arrival":None if dep is None else dep+6360,
        "actual_player_departure":0,
    }


def scheduled(dep,at):
    return {
        "status":"STABLE_3_COMMITMENT",
        "departure":dep,
        "committed_issue":at,
        "basis":"three_as_issued",
    }


class CommitmentReconfirmationTests(unittest.TestCase):
    def test_recent_fresh_reconfirmation(self):
        dep=T0+3600
        rows=[
            candidate(T0,dep),
            candidate(T0+300,dep),
            candidate(dep-220,dep)
        ]
        check=m.recheck_selected_departure(
            selection=scheduled(dep,T0+300),
            original=rows[0],rows=rows,
            times=[r["computed_at"] for r in rows],asof=dep+200)
        self.assertEqual(check["status"],
                         "RECONFIRMED_INSIDE_FRESH_5M_SNAPSHOT")
        self.assertEqual(check["drift_seconds"],0)
        self.assertTrue(check["departure_reached_asof"])

    def test_shifted_later_at_departure(self):
        dep=T0+3600
        rows=[
            candidate(T0,dep),
            candidate(T0+300,dep),
            candidate(dep-220,dep+1800),
        ]
        check=m.recheck_selected_departure(
            selection=scheduled(dep,T0+300),
            original=rows[0],rows=rows,
            times=[r["computed_at"] for r in rows],asof=dep+200)
        self.assertEqual(check["status"],"LATEST_FORECAST_SHIFTED_LATER")
        self.assertEqual(check["drift_seconds"],1800)

    def test_not_reached_does_not_use_future_replans(self):
        dep=T0+3600
        rows=[
            candidate(T0,dep),
            candidate(T0+300,dep),
            candidate(dep-100,dep+1800),
        ]
        check=m.recheck_selected_departure(
            selection=scheduled(dep,T0+300),
            original=rows[0],rows=rows,
            times=[r["computed_at"] for r in rows],asof=dep-300)
        self.assertEqual(check["status"],
                         "SCHEDULED_DEPARTURE_NOT_YET_REACHED")
        self.assertFalse(check["departure_reached_asof"])

    def test_no_nearby_and_invalid_last_tick_are_distinct(self):
        dep=T0+3600
        rows=[candidate(T0,dep),candidate(T0+300,dep)]
        t=[r["computed_at"] for r in rows]
        check=m.recheck_selected_departure(
            selection=scheduled(dep,T0+300),
            original=rows[0],rows=rows,times=t,asof=dep+200)
        self.assertEqual(
            check["status"],"NO_REPLAN_WITHIN_10M_OF_DEPARTURE")
        rows.append(candidate(dep-200,None,status="NO_RECOMMENDATION"))
        check=m.recheck_selected_departure(
            selection=scheduled(dep,T0+300),original=rows[0],
            rows=rows,times=[r["computed_at"] for r in rows],
            asof=dep+200)
        self.assertEqual(
            check["status"],"LATEST_REPLAN_INVALID_OR_ABSTAINED")

    def test_stable_target_but_snapshot_expired_is_not_fresh(self):
        dep=T0+3600
        rows=[candidate(T0,dep),
              candidate(T0+300,dep),
              candidate(dep-550,dep)]
        c=m.recheck_selected_departure(
            selection=scheduled(dep,T0+300),
            original=rows[0],rows=rows,
            times=[r["computed_at"] for r in rows],asof=dep+200)
        self.assertEqual(
            c["status"],"NEAR_SAME_TARGET_BUT_NOT_FRESHLY_EXECUTABLE")

    def test_full_audit_and_both_cli_report_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger=Path(tmp)/"forecast.sqlite"
            stock=Path(tmp)/"collector.sqlite"
            with sqlite3.connect(ledger) as con:
                con.execute("""CREATE TABLE v42_candidate_decisions(
                    id INTEGER PRIMARY KEY,item_key TEXT,
                    computed_at INTEGER,model_family TEXT,model_config TEXT,
                    stock_as_of INTEGER,status TEXT,
                    departure INTEGER,arrival INTEGER,
                    valid_until INTEGER,actual_player_departure INTEGER
                )""")
                samples=[
                    candidate(T0+300,T0+1800),
                    candidate(T0+600,T0+1800),
                    candidate(T0+900,T0+1800),
                    candidate(T0+1800-220,T0+1800+1800)
                ]
                con.executemany("""INSERT INTO v42_candidate_decisions(
                    item_key,computed_at,model_family,model_config,
                    stock_as_of,status,departure,arrival,
                    valid_until,actual_player_departure)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    [tuple(r[k] for k in (
                        "item_key","computed_at","model_family","model_config",
                        "stock_as_of","status","departure","arrival",
                        "valid_until","actual_player_departure")) for r in samples])
                con.commit()
            with sqlite3.connect(stock) as con:
                con.execute("CREATE TABLE check_table(x INTEGER)")
            def observe(*args):
                return "POLL_STATE_PROXY_SUCCESS",True,{}
            frozen_asof=T0+14000
            result=m.audit(
                ledger=ledger,stock=stock,now=frozen_asof,
                hours=12,keys=(ITEM,),scorer=observe)
            self.assertEqual(result["cohort_first_item_UTC_hour"],1)
            self.assertEqual(result["stable_commitment_selected"],1)
            self.assertEqual(result["fresh_selected"],0)
            self.assertEqual(result["stable_commitments_by_item"][ITEM][
                "by_latest_departure_recheck"]["LATEST_FORECAST_SHIFTED_LATER"][
                "arrival_stock_proxy_hit"],1)
            self.assertTrue(result["read_only"])
            self.assertTrue(result["late_rechecks_do_not_change_departure_selection"])
            real=m.audit
            def fixture(**kw):
                kw["now"]=frozen_asof
                return real(ledger=ledger,stock=stock,scorer=observe,**kw)
            with (patch.object(m,"audit",side_effect=fixture),
                  patch.object(m,"approved_collector_source",return_value=True)):
                for json_mode in (True,False):
                    argv=["v120","--hours","12","--items","nessie"]
                    if json_mode:argv.append("--json")
                    out=io.StringIO()
                    with (patch.object(sys,"argv",argv),
                          contextlib.redirect_stdout(out)):
                        m.main()
                    if json_mode:
                        val=json.loads(out.getvalue())
                        self.assertEqual(val["status"],
                          "V120_FIXED_ASOF_DEPARTURE_COMMITMENT_RECONFIRMATION")
                        self.assertEqual(val["stable_commitment_selected"],1)
                    else:
                        self.assertIn("V120 SAME V119 STABLE",out.getvalue())


if __name__=="__main__":
    unittest.main()
