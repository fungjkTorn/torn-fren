"""Small deterministic contracts for causal input handling."""
from pathlib import Path
import importlib.util,unittest
from collections import namedtuple
spec=importlib.util.spec_from_file_location('sample_api',Path(__file__).resolve().parents[1]/'services/reviewed_stock_samples.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
Obs=namedtuple('Obs','epoch quantity source')
class Samples(unittest.TestCase):
 def extract(self,rows,asof=1000,**kw):
  return m.repaired_stocked_windows(rows,asof=asof,since=100,retained_windows=[(1,20)],crosses_gap=kw.get('crosses',lambda a,b:False),fresh=kw.get('fresh',lambda at:True),verified_through=kw.get('verified',lambda a,b:a.epoch))
 def test_provider_switch_is_not_an_automatic_exclusion(self):
  rows=[Obs(100,0,'a'),Obs(130,2500,'b'),Obs(300,1800,'b'),Obs(600,0,'b')]
  self.assertEqual([(1,20),(130,600)],self.extract(rows))
 def test_supported_brief_return_is_one_closed_window(self):
  rows=[Obs(100,0,'a'),Obs(130,2500,'a'),Obs(300,1800,'a'),Obs(330,0,'a'),Obs(370,1700,'b'),Obs(600,0,'b')]
  self.assertEqual([(1,20),(130,600)],self.extract(rows))
 def test_pending_zero_not_yet_a_training_sample(self):
  rows=[Obs(100,0,'a'),Obs(130,2500,'a'),Obs(300,0,'a')]
  self.assertEqual([(1,20)],self.extract(rows,asof=350))
 def test_unknown_boundaries_are_not_qualified(self):
  rows=[Obs(100,0,'a'),Obs(400,2500,'b'),Obs(600,0,'b')]
  self.assertEqual([(1,20)],self.extract(rows))
 def test_real_collection_gap_is_not_continuous_stock(self):
  rows=[Obs(100,0,'a'),Obs(130,2500,'a'),Obs(300,1800,'a'),Obs(600,0,'a')]
  self.assertEqual([(1,20)],self.extract(rows,crosses=lambda a,b:a<450<b))
 def test_future_observation_rejected(self):
  with self.assertRaises(ValueError):self.extract([Obs(1001,0,'a')])
if __name__=='__main__':unittest.main()
