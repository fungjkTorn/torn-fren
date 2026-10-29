import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from deploy.scripts import repair_planner_evidence as installer
from services import first_release_evidence as ev
from test_first_release_live import make_issue,SHA


class PlannerRepairTests(unittest.TestCase):
    def test_known_v3_overlay_upgrade_blocks_duplicate_preview_before_live_changes(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);unit=base/'publisher.service';js=base/'beta.js'
            old_command=base/'reporting'/'98ebf83b2b87555dfca1'/'entry.py'
            unit.write_text('ExecStart=python '+str(old_command)+' publish\n')
            js.write_text('old UI');js.with_name('board.html').write_text('old board')
            (base/'latest.json').write_text(json.dumps({'model_sha':SHA,'published_epoch':100}))
            archive=base/'patch.zip'
            with zipfile.ZipFile(archive,'w') as z:
                for name in ('first_release_evidence','restock_signatures','simulated_trip_evidence'):
                    z.writestr('services/'+name+'.py',(Path('services')/(name+'.py')).read_bytes())
                z.writestr('web/first_release_assets/beta.js','new UI')
                z.writestr('web/first_release_assets/board.html','new board')
            original=unit.read_bytes()
            duplicate={'mex:Dahlia':{'target_identity_audit':{'duplicate_target_groups':1}}}
            with patch.object(installer,'BASE',base),patch.object(installer,'UNIT',unit),patch.object(installer,'JS',js),patch.object(installer,'preview',return_value=duplicate),patch.object(installer.os,'geteuid',return_value=0),patch.object(installer,'run') as run:
                result=installer.repair(archive,True)
            self.assertEqual('EVIDENCE_REPAIR_BLOCKED',result['status'])
            self.assertEqual(original,unit.read_bytes());self.assertEqual('old UI',js.read_text())
            run.assert_not_called()

    def test_private_preview_backfills_active_ten_without_writing_original_ledger(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);folder=base/'overlay';folder.mkdir()
            for original,target in [('first_release_evidence','evidence'),('restock_signatures','restock_signatures'),('simulated_trip_evidence','simulated_trip_evidence')]:
                (folder/(target+'.py')).write_bytes((Path('services')/(original+'.py')).read_bytes())
            ledger=base/'ledger.sqlite';db=ev.connect(ledger)
            for t in (100,200):
                for n in range(10):
                    row=make_issue('mex:Item'+str(n),t,t,t+100,0)
                    ev.record(db,row,model_sha=SHA)
                db.execute('INSERT INTO publications VALUES(?,?,?)',(t,t,'digest'))
            # An obsolete model must not overwrite the active cohort's metrics.
            ev.record(db,make_issue('mex:Old',50,50,150,0),model_sha='old')
            db.commit();db.close();original=ledger.read_bytes()
            source=base/'source.sqlite'
            with sqlite3.connect(source) as src:
                src.executescript('''CREATE TABLE stock_history(id INTEGER PRIMARY KEY,timestamp,country,item_name,quantity,source);
                    CREATE TABLE collection_gaps(start_timestamp,end_timestamp);
                    CREATE TABLE poll_heartbeats(timestamp,mode,success);
                    CREATE TABLE country_stock_observations(id INTEGER PRIMARY KEY,received_epoch,country,country_update_epoch,clock_status);''')
                for n in range(10):src.execute("INSERT INTO stock_history(timestamp,country,item_name,quantity,source) VALUES(10,'mex',?,100,'a')",('Item'+str(n),))
                for t in range(10,501,10):
                    src.execute("INSERT INTO poll_heartbeats VALUES(?,'poll-cycle',1)",(t,))
                    src.execute("INSERT INTO country_stock_observations(received_epoch,country,country_update_epoch,clock_status) VALUES(?,'mex',?,'REPORTED')",(t,t))
            with patch.object(installer,'BASE',base):result=installer.preview(folder,ledger,source,SHA)
            self.assertEqual(10,len(result));self.assertNotIn('mex:Old',result)
            self.assertTrue(all(m['simulated_trips_total']==1 and m['successes']==1 for m in result.values()))
            self.assertEqual(original,ledger.read_bytes())

    def test_failed_publication_restores_unit_ui_snapshot_and_keeps_ledger(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);base=root/'state';base.mkdir();unit=root/'publisher.service';js=root/'beta.js'
            unit.write_text('ExecStart=python -m services.first_release_live publish\n');js.write_text('old UI')
            js.with_name('board.html').write_text('old board')
            snapshot=json.dumps({'model_sha':'frozen','published_epoch':100}).encode();(base/'latest.json').write_bytes(snapshot)
            with sqlite3.connect(base/'forecasts.sqlite') as con:con.execute('CREATE TABLE evidence(value)');con.execute("INSERT INTO evidence VALUES('preserved')")
            original_unit=unit.read_bytes();original_db=(base/'forecasts.sqlite').read_bytes()
            archive=root/'patch.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('services/first_release_evidence.py','X=1\n');z.writestr('web/first_release_assets/beta.js','new UI')
                z.writestr('services/restock_signatures.py','X=1\n');z.writestr('services/simulated_trip_evidence.py','X=1\n')
                z.writestr('web/first_release_assets/board.html','new board')
            def run(args,timeout=30):
                if args==['systemctl','start',unit.name]:(base/'latest.json').write_text(json.dumps({'model_sha':'WRONG','published_epoch':200}))
                return ''
            with patch.object(installer,'BASE',base),patch.object(installer,'UNIT',unit),patch.object(installer,'JS',js),patch.object(installer,'BACKUPS',root/'backup'),patch.object(installer,'run',side_effect=run),patch.object(installer,'preview',return_value={}),patch.object(installer,'reconcile',return_value={}),patch.object(installer.os,'geteuid',return_value=0):
                self.assertEqual('EVIDENCE_REPAIR_PLAN',installer.repair(archive)['status'])
                result=installer.repair(archive,True)
            self.assertEqual('EVIDENCE_REPAIR_ROLLED_BACK',result['status'])
            self.assertEqual(original_unit,unit.read_bytes());self.assertEqual('old UI',js.read_text())
            self.assertEqual(snapshot,(base/'latest.json').read_bytes())
            self.assertEqual('old board',js.with_name('board.html').read_text())
            self.assertEqual(original_db,(base/'forecasts.sqlite').read_bytes())

    def test_reconcile_earlier_failure_preserving_existing_logs_and_target(self):
        with tempfile.TemporaryDirectory() as td:
            db=ev.connect(Path(td)/'ledger.db');source=sqlite3.connect(':memory:')
            source.executescript('CREATE TABLE stock_history(id INTEGER PRIMARY KEY,timestamp,country,item_name,quantity,source); CREATE TABLE collection_gaps(start_timestamp,end_timestamp);')
            source.executemany('INSERT INTO stock_history VALUES(?,?,?,?,?,?)',[(1,100,'mex','Dahlia',0,'a'),(2,140,'mex','Dahlia',0,'b'),(3,200,'mex','Dahlia',100,'b')])
            for issued,status in [(110,'FAILURE'),(150,'SUCCESS')]:
                row=make_issue('mex:Dahlia',issued,180,200)
                ev.record(db,row,model_sha=SHA)
                db.execute('INSERT INTO publications VALUES(?,?,?)',(issued,issued,SHA))
                db.execute('INSERT INTO outcomes VALUES(?,?,?,?)',('mex:Dahlia',issued,400,json.dumps({'status':status})))
            target=ev.target_for_issue(make_issue('mex:Dahlia',150,180,200),[(100,0,'a'),(140,0,'b'),(200,100,'b')],[])
            db.execute('INSERT INTO target_links VALUES(?,?,?)',('mex:Dahlia',150,json.dumps(target)))
            before={table:db.execute('SELECT * FROM '+table).fetchall() for table in ('issues','outcomes')}
            saved=db.execute('SELECT payload FROM target_links WHERE issued=150').fetchone()[0]
            result=ev.legacy_summary(db,source,item_key='mex:Dahlia',model_sha=SHA,cutoff=400)
            self.assertEqual(1,result['failures']);self.assertEqual(0,result['successes'])
            self.assertEqual(110,result['trips'][0]['issued_epoch'])
            self.assertEqual(2,result['recorded_forecast_revisions'])
            for table,rows in before.items():self.assertEqual(rows,db.execute('SELECT * FROM '+table).fetchall())
            self.assertEqual(saved,db.execute('SELECT payload FROM target_links WHERE issued=150').fetchone()[0])
            self.assertEqual(2,db.execute('SELECT COUNT(*) FROM target_links').fetchone()[0])


if __name__=='__main__':unittest.main()
