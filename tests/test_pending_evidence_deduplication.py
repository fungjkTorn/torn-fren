"""Keep one pending outcome per immutable issue without blocking resolution."""
import json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from services import first_release_evidence as ev
class PendingEvidenceDeduplication(unittest.TestCase):
 def test_pending_is_not_repeated_and_final_resolution_is_retained(self):
  with tempfile.TemporaryDirectory() as td:
   db=ev.connect(Path(td)/'ledger.sqlite');src=sqlite3.connect(':memory:')
   src.executescript('CREATE TABLE stock_history(id INTEGER PRIMARY KEY,timestamp INTEGER,quantity INTEGER,source TEXT,country TEXT,item_name TEXT);CREATE TABLE poll_heartbeats(timestamp INTEGER,mode TEXT,success INTEGER);CREATE TABLE collection_gaps(start_timestamp INTEGER,end_timestamp INTEGER);')
   issue={'item_key':'mex:Dahlia','asof_epoch':100,'decision':{'estimated_departure_epoch':200,'estimated_arrival_epoch':1000,'selected_restock_event_index':1,'forecast_events':[]}}
   ev.record(db,issue,model_sha='a'*40);db.execute('INSERT INTO publications VALUES(100,100,?)',('a'*40,));before=db.execute('SELECT payload FROM issues').fetchone()[0]
   with patch.object(ev,'grade',side_effect=[{'status':'PENDING'},{'status':'PENDING'},{'status':'SUCCESS'}]):
    for cutoff in [101,102]:ev.score(db,src,cutoff=cutoff,model_sha='a'*40)
    self.assertEqual(db.execute('SELECT COUNT(*) FROM outcomes').fetchone()[0],1)
    ev.score(db,src,cutoff=1200,model_sha='a'*40)
   self.assertEqual(db.execute('SELECT COUNT(*) FROM outcomes').fetchone()[0],2)
   self.assertEqual(json.loads(db.execute('SELECT payload FROM outcomes ORDER BY cutoff DESC LIMIT 1').fetchone()[0])['status'],'SUCCESS')
   self.assertEqual(db.execute('SELECT payload FROM issues').fetchone()[0],before)
   db.close();src.close()
if __name__=='__main__':unittest.main()
