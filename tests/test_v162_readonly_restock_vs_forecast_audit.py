"""V162 confirms lifetime observed restocks != recently eligible V160 forecasts."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_v160_prospective_v151_shadow import T,collector_fixture,model
from research.v160_prospective_v151_shadow import capture_once

from importlib.util import spec_from_file_location,module_from_spec
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"deploy/scripts/v162_readonly_restock_vs_forecast_audit.py"
spec=spec_from_file_location("v162_restock_audit",SCRIPT)
audit_module=module_from_spec(spec)
spec.loader.exec_module(audit_module)


class RestockAuditTests(unittest.TestCase):
    def test_change_only_repeated_zero_is_not_multiple_restocks(self):
        start=100
        rows=[
            (110,0,"yata",1),(120,0,"yata",2),
            (130,40,"yata",3),(140,40,"yata",4),
            (150,0,"yata",5),(160,0,"yata",6),
            (170,50,"yata",7)]
        out=audit_module.restock_edges(rows,window_start=start,gaps=[])
        self.assertEqual(out["observed_threshold_restocks"],2)
        self.assertEqual(out["observed_depletions_below_30"],1)
        self.assertEqual(out["same_provider_positive_quantity_changes"],2)
        self.assertEqual(out["delta_rows"],7)

    def test_provider_switch_threshold_and_known_gap_not_invented(self):
        rows=[
            (110,0,"yata",1),(120,100,"prometheus",2),
            (130,0,"prometheus",3),(200,100,"prometheus",4),
            (220,0,"prometheus",5),(240,100,"prometheus",6)]
        out=audit_module.restock_edges(
            rows,window_start=100,gaps=[(190,195)])
        self.assertEqual(out["ambiguous_cross_provider_threshold_changes"],1)
        self.assertEqual(out["known_gap_edges"],1)
        self.assertEqual(out["observed_threshold_restocks"],1)
        self.assertEqual(out["observed_depletions_below_30"],2)

    def test_true_historical_restock_count_exceeds_recent_forecast_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=collector_fixture(root)
            ledger=root/"v160_v151_prospective24.db"
            # Add repeated observed threshold transitions for Nessie
            # WITHIN the historical period, but V160 only issues once.
            with sqlite3.connect(source) as db:
                for i in range(8):
                    t=T-7200+i*300
                    db.execute(
                        """INSERT INTO stock_history(timestamp,quantity,source,country,item_name)
                           VALUES(?,?,?,?,?)""",
                        (t,0 if i%2==0 else 200,"yata","uni","Nessie Plushie"))
            with patch("research.v160_prospective_v151_shadow.stable_earliest_departure",
                       side_effect=model):
                capture_once(source=source,destination=ledger,canonical=False,
                             now_fn=lambda:T,mono_fn=lambda:10,
                             record=True,issued_epoch=T,scenarios=8)
            before=source.read_bytes()
            outcome=audit_module.audit(collector=source,ledger=ledger,
                       roster=ROOT/"research/v38_roster.json",now=T,days=7)
            nessie=outcome["items"]["uni:Nessie Plushie"]
            self.assertGreaterEqual(nessie["observed_threshold_restocks"],4)
            self.assertEqual(nessie["v160_five_minute_issues"],1)
            self.assertEqual(nessie["v160_independent_proposals"],1)
            self.assertEqual(outcome["v160_issue_batches"],1)
            self.assertEqual(len(outcome["items"]),24)
            self.assertFalse(outcome["collector_and_sidecar_written"])
            self.assertEqual(source.read_bytes(),before)
            out=audit_module.summary(outcome)
            self.assertIn("uni:Nessie Plushie DIAGNOSTIC",out)
            self.assertIn("jap:Xanax DIAGNOSTIC",out)
            self.assertIn("V160 ISSUES",out)

    def test_xanax_zero_departures_is_visible_as_status_not_missing_restock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=collector_fixture(root)
            ledger=root/"v160_v151_prospective24.db"
            with patch("research.v160_prospective_v151_shadow.stable_earliest_departure",
                       side_effect=model):
                capture_once(source=source,destination=ledger,canonical=False,
                             now_fn=lambda:T,mono_fn=lambda:10,
                             record=True,issued_epoch=T,scenarios=8)
            with sqlite3.connect(ledger) as db:
                row=db.execute("SELECT payload_json FROM v160_issued WHERE item_key=?",
                               ("jap:Xanax",)).fetchone()
                v=json.loads(row[0])
                for m in v["models"].values():
                    m.update(departure_epoch=None,arrival_epoch=None,
                             wait_seconds=None,scenario_fraction=None,
                             status="NO_TWO_BIN_SUPPORTED_DEPARTURE")
                db.execute("UPDATE v160_issued SET payload_json=? WHERE item_key=?",
                           (json.dumps(v),"jap:Xanax"))
            r=audit_module.audit(collector=source,ledger=ledger,
                                 roster=ROOT/"research/v38_roster.json",now=T,days=7)
            j=r["items"]["jap:Xanax"]
            self.assertEqual(j["v160_independent_proposals"],0)
            self.assertEqual(j["v160_paired_proposals"],0)
            self.assertEqual(j["v160_independent_statuses"],
                             {"NO_TWO_BIN_SUPPORTED_DEPARTURE":1})
            self.assertGreater(j["observed_threshold_restocks"],0)


if __name__=="__main__":
    unittest.main()
