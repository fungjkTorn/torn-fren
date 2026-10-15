import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research import continuous_departure_replay as m

T=1791910800


class EvidenceTests(unittest.TestCase):
    def evidence(self, rows, polls=(990,1020), gaps=(), cutoff=2000):
        return m.ArrivalEvidence([m.model.OBS(*r) for r in rows],list(polls),gaps,cutoff)

    def test_unchanged_delta_stock_is_valid_and_missing_polls_unknown(self):
        e=self.evidence([(100,200,"yata")])
        self.assertEqual(e.score(1000)[0],"SUCCESS")
        self.assertEqual(self.evidence([(100,0,"yata")]).score(1000)[0],"FAILURE")
        self.assertEqual(self.evidence([(100,200,"yata")],polls=()).score(1000)[0],"UNKNOWN")
        self.assertEqual(self.evidence([(100,200,"yata")],cutoff=1100).score(1000)[0],"PENDING")

    def test_hidden_sellout_restock_and_provider_switch_are_unknown(self):
        rows=[(100,200,"yata"),(1001,0,"yata"),(1009,200,"yata")]
        self.assertEqual(self.evidence(rows).score(1000)[1],"THRESHOLD_TRANSITION_IN_BRACKET")
        self.assertEqual(self.evidence([(100,200,"yata"),(1001,200,"other")]).score(1000)[1],"ITEM_PROVIDER_SWITCH")
        self.assertEqual(self.evidence([(100,200,"yata")],gaps=[(1001,1002)]).score(1000)[1],"COLLECTION_GAP")

    def test_training_minute_rejects_excursions_between_good_endpoints(self):
        polls=(990,1010,1050,1070)
        for rows,gaps in (([(100,200,'a'),(1020,0,'a'),(1040,200,'a')],()),
                          ([(100,200,'a'),(1020,200,'b'),(1040,200,'a')],()),
                          ([(100,200,'a')],[(1020,1040)])):
            e=self.evidence(rows,polls=polls,gaps=gaps)
            self.assertEqual(e.score(1000)[0],'SUCCESS')
            self.assertEqual(e.score(1060)[0],'SUCCESS')
            self.assertEqual(e.interval_score(1000,1060),-1)


class ContinuousTests(unittest.TestCase):
    def fixture(self, directory):
        from test_v160_prospective_v151_shadow import collector_fixture
        db=collector_fixture(directory,issued=T)
        with sqlite3.connect(db) as cx:
            cx.execute("DELETE FROM stock_history")
            cx.execute("DELETE FROM poll_heartbeats")
            cx.execute("CREATE TABLE research_metadata(key TEXT PRIMARY KEY,value TEXT)")
            cx.execute("INSERT INTO research_metadata VALUES('source_cutoff_epoch',?)",(str(T),))
            start=T-3*86400
            for key in m.model.exact_roster():
                country,name=key.split(":",1)
                cx.executemany("INSERT INTO stock_history(timestamp,quantity,source,country,item_name) VALUES(?,?,?,?,?)",
                    [(start+i*1200+offset,q,"yata",country,name) for i in range(216)
                     for offset,q in ((0,0),(600,200),(900,0))])
            cx.executemany("INSERT INTO poll_heartbeats(timestamp,mode,success) VALUES(?,'poll-cycle',1)",
                           [(p,) for p in range(start,T+1,30)])
        return db

    def test_all_issues_readonly_frozen_decisions_and_denominators(self):
        with tempfile.TemporaryDirectory() as td:
            db=self.fixture(Path(td)); before=db.read_bytes(); journal=io.StringIO()
            real=m.model.predict_events
            def causal(key,phase,*,asof,**kw):
                self.assertLessEqual(phase["last_observation"].epoch,asof)
                return real(key,phase,asof=asof,**kw)
            with patch.object(m.model,"predict_events",side_effect=causal):
                report=m.replay(source=db,days=1,limit_items=1,journal=journal,model_sha="fixture")
            self.assertEqual(before,db.read_bytes())
            records=[json.loads(x) for x in journal.getvalue().splitlines()]
            self.assertEqual(len(records),288*len(m.POLICIES))
            self.assertEqual(len({r["issue_id"] for r in records}),len(records))
            self.assertFalse(report["future_truth_selects_issue_times"])
            families=report['event_models_fixed_four_hour']
            self.assertGreater(families['v163']['observed'],0)
            self.assertEqual(families['v163']['observed'],families['daily_template']['observed'])
            depleted=report['depletion_models_fixed_four_hour']
            self.assertGreater(depleted['v163']['observed'],0)
            self.assertEqual(len({v['observed'] for v in depleted.values()}),1)
            self.assertTrue(depleted['zero_anchored']['prediction_supported'])
            self.assertTrue(depleted['zero_rate']['prediction_supported'])
            self.assertIsNone(depleted['v163']['recall_10m'])
            self.assertIn('availability_loss_models_fixed_four_hour',report)
            self.assertTrue(all(v['matched_600s']<=min(v['observed'],v['forecast']) for v in depleted.values()))
            for policy,c in report["policies"].items():
                self.assertEqual(c["issues"],288)
                rc=report["items"][next(iter(report["items"]))]["policies"][policy]["replanned_hourly_starts"]
                self.assertEqual(rc["starts"],24)
                detail=report["items"][next(iter(report["items"]))]["policies"][policy]
                self.assertEqual(detail["replanned_utc_hourly_starts"]["starts"],24)
                pooled=detail["replanned_all_five_minute_starts"]
                self.assertEqual(pooled["starts"],288)
                self.assertEqual(len(pooled["offsets"]),12)
                self.assertEqual(sum(rc.get(k,0) for k in ("SUCCESS","FAILURE","PENDING","UNKNOWN","ABSTAIN")),24)
                self.assertEqual(sum(c.get(k,0) for k in ("SUCCESS","FAILURE","PENDING","UNKNOWN","ABSTAIN")),288)
                self.assertEqual(c["proposals"]+c.get("ABSTAIN",0),288)
            item=next(iter(report["items"].values()))
            self.assertEqual(len(item["path_established_reference_comparisons"]),13)
            self.assertTrue(all(v["starts"]==288 for refs in item["path_all_start_established_reference_comparisons"].values() for v in refs.values()))
            self.assertTrue(all(v["starts"]==24 for refs in item["path_established_reference_comparisons"].values() for v in refs.values()))
            self.assertEqual(len(item["matched_zero_replanned_comparisons"]),len(m.ZERO_COMPARATORS))
            for c in item["matched_zero_replanned_comparisons"].values():
                self.assertEqual(c["starts"],24)
                self.assertLessEqual(c.get("matched_resolved",0),24)
            for c in item["matched_v166_comparisons"].values():
                self.assertLessEqual(c.get("matched_issues",0),288)
                self.assertLessEqual(c.get("challenger_only_success",0)+c.get("v166_only_success",0),c.get("matched_issues",0))
            with patch.object(m,"stable_earliest_departure",side_effect=AssertionError("unused V151")):
                focused=m.replay(source=db,days=1,limit_items=1,model_sha="fixture",focused_zero=True)
            self.assertNotIn("v151_independent_48",focused["policies"])
            for section in ("event_models_fixed_four_hour","depletion_models_fixed_four_hour","availability_loss_models_fixed_four_hour"):
                self.assertEqual(focused[section],report[section])
            for policy,value in focused["items"][next(iter(focused["items"]))]["policies"].items():
                self.assertEqual(value,item["policies"][policy])
            # Alter only post-issue truth. The earlier forecast and chosen
            # departure must remain identical while evaluation may change.
            split=T-43200
            with sqlite3.connect(db) as cx:
                cx.execute("UPDATE stock_history SET quantity=0 WHERE timestamp>?",(split,))
            other=io.StringIO()
            m.replay(source=db,days=1,limit_items=1,journal=other,model_sha="fixture")
            changed=[json.loads(x) for x in other.getvalue().splitlines()]
            fields=("issue_id","issued_epoch","departure_epoch","arrival_epoch","forecast_events","status","selected_expert","selector_evidence","path_evidence")
            for a,b in zip(records,changed):
                if a["issued_epoch"]<=split:
                    self.assertEqual({k:a[k] for k in fields},{k:b[k] for k in fields})

    def test_fixed_issue_window_preserves_forecasts_while_truth_matures(self):
        with tempfile.TemporaryDirectory() as td:
            db=self.fixture(Path(td));end=T-14400
            before=io.StringIO();after=io.StringIO()
            m.replay(source=db,days=1,asof=end,limit_items=1,journal=before,
                     model_sha="fixed",focused_zero=True)
            r=m.replay(source=db,days=1,asof=T,issue_end=end,limit_items=1,journal=after,
                       model_sha="fixed",focused_zero=True)
            a=[json.loads(x) for x in before.getvalue().splitlines()]
            b=[json.loads(x) for x in after.getvalue().splitlines()]
            self.assertEqual(len(a),len(b))
            fields=("issue_id","issued_epoch","departure_epoch","forecast_events","path_evidence","selector_evidence")
            for left,right in zip(a,b):
                self.assertLessEqual(right["issued_epoch"],end)
                self.assertEqual({k:left[k] for k in fields},{k:right[k] for k in fields})
            self.assertEqual(r["issue_window_end_epoch"],end)
            self.assertEqual(r["asof_epoch"],T)
            item=next(iter(r["items"].values()))
            self.assertTrue(item["post_window_replanning_plans"])
            self.assertTrue(all(v["replanned_hourly_starts"]["starts"]==24 for v in item["policies"].values()))
            self.assertLessEqual(sum(x["outcome"]=="PENDING" for x in b),sum(x["outcome"]=="PENDING" for x in a))
            with self.assertRaises(ValueError):m.replay(source=db,days=1,issue_end=T+1,limit_items=1)

    def test_missing_heartbeat_abstains_and_cutoff_is_snapshot_not_wallclock(self):
        with tempfile.TemporaryDirectory() as td:
            db=self.fixture(Path(td))
            with sqlite3.connect(db) as cx:
                cx.execute("DELETE FROM poll_heartbeats")
            report=m.replay(source=db,days=1,limit_items=1)
            self.assertEqual(report["asof_epoch"],T)
            self.assertTrue(all(c.get("ABSTAIN")==288 for c in report["policies"].values()))
            with self.assertRaises(ValueError):
                m.replay(source=db,days=1,asof=T+1,limit_items=1)

    def test_known_active_outage_abstains_even_with_global_heartbeat(self):
        with tempfile.TemporaryDirectory() as td:
            db=self.fixture(Path(td)); stream=io.StringIO()
            with sqlite3.connect(db) as cx:
                cx.execute("INSERT INTO collection_gaps VALUES(?,NULL)",(T-3600,))
            m.replay(source=db,days=1,limit_items=1,journal=stream)
            records=[json.loads(r) for r in stream.getvalue().splitlines()]
            active=[r for r in records if r["issued_epoch"]>=T-3600]
            self.assertTrue(active)
            self.assertTrue(all(r["outcome"]=="ABSTAIN" and r["departure_epoch"] is None for r in active))


if __name__=="__main__":
    unittest.main()
