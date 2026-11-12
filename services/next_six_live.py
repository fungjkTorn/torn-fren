"""Isolated publisher for six approved baseline additions."""
import argparse,json,time
from pathlib import Path
from services.forward_beta_roster import NEXT_SIX_MODELS
from services.first_release_live import publish
from services.first_release_source import refresh_tail

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--collector',required=True)
 p.add_argument('--state',required=True);p.add_argument('--source');p.add_argument('--model-sha',required=True)
 a=p.parse_args();state=Path(a.state);source=Path(a.source) if a.source else state/'stock_history.sqlite'
 started=time.monotonic()
 info=refresh_tail(source,a.collector,cutoff=int(time.time()),model_roster=NEXT_SIX_MODELS)
 result=publish(source,state,model_sha=a.model_sha,publisher_sha=a.model_sha,model_roster=NEXT_SIX_MODELS,
  time_budget_seconds=90,item_timeout_seconds=45,next_six_cohort=True)
 result['source_refresh']=info;result['total_elapsed_seconds']=round(time.monotonic()-started,3)
 print(json.dumps(result))

if __name__=='__main__':main()
