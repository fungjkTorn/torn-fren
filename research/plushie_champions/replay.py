from __future__ import annotations
import argparse, importlib, json
TARGETS={
 'nessie':('recent_phase_select','replay'),
 'redfox':('rf_localgrid','replay'),
 'lion':('lion_pair_selector_ml','replay'),
 'panda':('panda_pair_selector_ml','replay'),
 'camel':('camel_fast_selector','replay'),
}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--db',required=True);ap.add_argument('--target',choices=[*TARGETS,'monkey','chamois','all'],default='all');a=ap.parse_args();todo=[a.target] if a.target!='all' else ['nessie','redfox','lion','panda','monkey','chamois','camel'];out={}
 for t in todo:
  if t in ('monkey','chamois'):
   m=importlib.import_module('checkpoint4_online_selector');c,i=m.TARGETS[t];out[t]=m.replay_target(a.db,c,i)
  else:
   mod,fn=TARGETS[t];out[t]=getattr(importlib.import_module(mod),fn)(a.db)
 print(json.dumps(out,indent=2,default=str))
if __name__=='__main__':main()
