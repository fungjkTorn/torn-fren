"""Synthetic browser-test fixture only; never production stock."""
import json
import sys
import time
from services.travel_read_model import build_board

now=int(time.time())
source={"asof_epoch":now,"source_heartbeat_age_seconds":10,"items":{}}
for country,name,flight,qty,wait in [
    ('mex','Jaguar Plushie',1020,2100,1200),('uni','Nessie Plushie',6360,0,2400),
    ('jap','Xanax',8940,0,3600),('cay','Banana Orchid',1380,820,4200),
    ('chi','Panda Plushie',9600,1300,1800),('arg','Ceibo Flower',6660,1520,4800)]:
    start=now+flight+wait+10
    source['items'][country+':'+name]={"asof_epoch":now,"item_key":country+':'+name,
        "status":"EVENT_TIMELINE_FORECAST_AVAILABLE","flight_seconds":flight,
        "observed_current_quantity":qty,"last_quantity_change_epoch":now-800,
        "current_stock_window":None,"restock_events":[{
            "predicted_restock_epoch":start+i*4800,"restock_early_epoch":start+i*4800-400,
            "restock_late_epoch":start+i*4800+500,"predicted_stock_below_30_epoch":start+i*4800+1500
        } for i in range(3)]}
source['model_sha']='a'*40
source['item_departure_recommendations']={'chi:Panda Plushie':{
    'item_key':'chi:Panda Plushie','asof_epoch':now,'model_sha':'a'*40,
    'policy':'zero_path_analog80','model_name':'causal_complete_stock_paths_v1',
    'player_flight_seconds':9600,'target_quantity':30,'depletion_stock_quantity':0,
    'event_timing_prediction_supported':False,'departure_epoch':now+1800,
    'status':'HISTORICAL_PATH_PROPOSAL'}}
overrides={sys.argv[1]:int(sys.argv[2])} if len(sys.argv)>2 else None
data=build_board(source,now=now,flight_overrides=overrides)
data['test_fixture']=True
print(json.dumps(data))
