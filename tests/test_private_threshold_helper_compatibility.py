"""Preserve production helper thresholds and default historical behavior."""
import sqlite3,unittest
from research.quantity_rate_cycles import QuantityRateCycles
from research.true_zero_cycles import ZeroCycles,model
from research.plushie_champions.common import Timeline

class ThresholdHelperCompatibilityTests(unittest.TestCase):
 def feed(self,tracker):
  for t,q in [(1,0),(100,100),(200,31),(300,30),(400,29),(500,0)]:tracker.add(model.OBS(t,q,'yata'))
  return tracker
 def test_zero_cycle_31_keyword_and_legacy_default(self):
  legacy=self.feed(ZeroCycles(lambda a,b:False))
  strict=self.feed(ZeroCycles(lambda a,b:False,min_qty=31))
  self.assertEqual(legacy.available_durations,[300]);self.assertEqual(strict.available_durations,[200])
  self.assertEqual(legacy.zero_onset_bracket,strict.zero_onset_bracket)
  self.assertEqual(legacy.min_qty,30);self.assertEqual(strict.min_qty,31)
 def test_quantity_rate_31_keyword_and_legacy_default(self):
  legacy=self.feed(QuantityRateCycles(lambda a,b:False))
  strict=self.feed(QuantityRateCycles(lambda a,b:False,min_qty=31))
  self.assertEqual(legacy.available_durations,[300]);self.assertEqual(strict.available_durations,[200])
  self.assertEqual(list(legacy.rates),list(strict.rates))
 def test_timeline_31_keyword_preserves_legacy_default(self):
  with sqlite3.connect(':memory:') as db:
   db.execute('CREATE TABLE stock_history(id INTEGER PRIMARY KEY,timestamp INTEGER,quantity INTEGER,source TEXT,country TEXT,item_name TEXT)')
   db.executemany('INSERT INTO stock_history(timestamp,quantity,source,country,item_name) VALUES(?,?,?,?,?)',[(t,q,'yata','swi','Chamois Plushie') for t,q in [(1,0),(100,100),(200,31),(300,30),(400,29),(500,0)]])
   old=Timeline(db,[],[],'swi','Chamois Plushie');strict=Timeline(db,[],[],'swi','Chamois Plushie',min_qty=31)
   self.assertEqual(old.vals([300])[0][0],1);self.assertEqual(strict.vals([300])[0][0],0)
 def test_invalid_threshold_rejected(self):
  for q in (0,-1,True,1.2):
   with self.assertRaises(ValueError):ZeroCycles(lambda a,b:False,min_qty=q)

if __name__=='__main__':unittest.main()
