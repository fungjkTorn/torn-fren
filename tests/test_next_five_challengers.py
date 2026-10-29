from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from research.corrected_challengers import NEXT_MODELS,ALL_MODELS,forecast
from services.first_release_schedule import build_first_release_decision
from test_first_release_schedule import NOW,event,forecast as events,FirstReleaseNativeTests as Fixture


class NextFiveTests(unittest.TestCase):
    def test_sequence_and_actual_native_engines(self):
        Fixture.setUpClass()
        try:
            with tempfile.TemporaryDirectory() as td:
                source=Path(td)/'next.sqlite';shutil.copyfile(Fixture.source,source)
                with sqlite3.connect(source) as c:
                    rows=c.execute("SELECT timestamp,quantity,source FROM stock_history WHERE country='can' AND item_name='Crocus'").fetchall()
                    for key in NEXT_MODELS:
                        country,item=key.split(':',1)
                        c.executemany('INSERT INTO stock_history(timestamp,country,item_name,quantity,source) VALUES(?,?,?,?,?)',[(t,country,item,q,s) for t,q,s in rows])
                before=source.read_bytes()
                for key,identity in NEXT_MODELS.items():
                    d=build_first_release_decision(events(key,[event(NOW+100,200),event(NOW+10000),event(NOW+20000)]),
                        now=NOW,flight_seconds=1200,poll_age_seconds=0,model_roster=ALL_MODELS,timing_choice=lambda **kw:None)
                    self.assertEqual(2,d['selected_restock_event_index'])
                    self.assertEqual(NOW+8800,d['estimated_departure_epoch'])
                    result=forecast(source,key,NOW);d=result['decision']
                    self.assertEqual(identity,(d['timing_model_generation'],d['timing_model_config']))
                    self.assertTrue(result['timing_full_history_override'])
                    self.assertEqual(31,d['target_quantity']);self.assertEqual(0,d['arrival_grace_seconds'])
                self.assertEqual(before,source.read_bytes())
        finally:Fixture.tearDownClass()


if __name__=='__main__':unittest.main()
