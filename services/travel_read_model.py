"""Bounded precomputed event read-model for all three player views.

No collector access or model execution per request. Optional assignments
are explicit per-item research policies; an evaluation winner never
automatically changes an assignment.
"""
import json
import threading
from pathlib import Path
from urllib.parse import urlencode

from services.travel_window_policy import project_policy

COUNTRIES={"arg":"Argentina","can":"Canada","cay":"Cayman Islands","chi":"China",
           "haw":"Hawaii","jap":"Japan","mex":"Mexico","sou":"South Africa",
           "swi":"Switzerland","uae":"UAE","uni":"United Kingdom"}
FLOWERS=frozenset(("Ceibo Flower","Crocus","Banana Orchid","Peony","Orchid",
                  "Cherry Blossom","Dahlia","African Violet","Edelweiss","Tribulus Omanense","Heather"))
MAX_BYTES=16*1024*1024


def category(name):
    return "Plushies" if "Plushie" in name else "Flowers" if name in FLOWERS else "Medication" if name=="Xanax" else "Other"


def build_board(snapshot,*,now,flight_overrides=None):
    if not isinstance(snapshot,dict) or not isinstance(snapshot.get("items"),dict) or len(snapshot["items"])>250:
        raise ValueError("invalid bounded event snapshot")
    issued=snapshot.get("asof_epoch")
    if type(issued) is not int or issued>now+15:
        raise ValueError("invalid snapshot timestamp")
    age=snapshot.get("source_heartbeat_age_seconds")
    age=age+max(0,now-issued) if type(age) is int and age>=0 else None
    overrides=flight_overrides or {}
    assignments=snapshot.get("item_policies",{})
    evidence=snapshot.get("item_evidence",{})
    rows=[]
    for key,forecast in sorted(snapshot["items"].items()):
        country,name=key.split(":",1)
        policy=assignments.get(key,"median")
        if not isinstance(forecast,dict) or forecast.get("item_key")!=key or forecast.get("asof_epoch")!=issued:
            raise ValueError("mixed issue or item identities")
        decision=project_policy(forecast,now=now,poll_age_seconds=age,kind=policy,
            player_flight_seconds=overrides.get(country))
        record=evidence.get(key)
        study=None
        if isinstance(record,dict):
            hits=record.get("successes"); n=record.get("resolved_arrivals")
            if type(hits) is int and type(n) is int and 0<=hits<=n and n>0:
                study={"successes":hits,"resolved_arrivals":n,"historical_fraction":hits/n,
                       "label":"Historical sampled-arrival study",
                       "policy":record.get("policy"),
                       "matches_selected_policy":record.get("policy")==policy,
                       "matches_selected_flight":record.get("player_flight_seconds")==decision['player_flight_seconds'],
                       "matches_selected_model":bool(snapshot.get('model_sha')) and record.get('model_sha')==snapshot.get('model_sha'),
                       "prospective_certified":False}
                study['applies_to_selected_trip']=(study['matches_selected_policy']
                    and study['matches_selected_flight'] and study['matches_selected_model'])
        depart=decision["estimated_departure_epoch"]
        landing=depart+decision["player_flight_seconds"] if depart is not None else None
        rows.append({"item_key":key,"country":country,"country_name":COUNTRIES.get(country,country),
                     "item_name":name,"category":category(name),
                     "observed_quantity":forecast.get("observed_current_quantity"),
                     "last_quantity_change_epoch":forecast.get("last_quantity_change_epoch"),
                     "model_name":snapshot.get("model_version","V163 event forecast"),
                     "policy":policy,"evidence":study,"decision":decision,
                     "departure_epoch":depart,"arrival_epoch":landing,
                     "departure_deadline_epoch":decision["estimated_departure_deadline_epoch"],
                     "graph_url":"/?"+urlencode({"country":country,"item":name}),
                     "quality_label":"Research estimate — recheck before travel",
                     "arrival_stock_quantity_prediction":None})
    return {"schema_version":1,"status":"RESEARCH_PREVIEW","asof_epoch":issued,"evaluated_at_epoch":now,
            "source_poll_age_seconds":age,"rows":rows,"item_count":len(rows),
            "personalization_requires_api_key":False,"calibrated_arrival_probability_available":False}


class SnapshotCache:
    def __init__(self):
        self.lock=threading.Lock(); self.signature=None; self.value=None

    def read(self,path):
        p=Path(path)
        with self.lock:
            stat=p.stat()
            if not p.is_file() or stat.st_size>MAX_BYTES:
                raise ValueError("invalid event snapshot file")
            signature=(str(p.resolve()),stat.st_ino,stat.st_mtime_ns,stat.st_size)
            if signature!=self.signature:
                with p.open("rb") as stream:
                    content=stream.read(MAX_BYTES+1)
                if len(content)>MAX_BYTES:
                    raise ValueError("oversized event snapshot")
                value=json.loads(content)
                self.signature,self.value=signature,value
            return self.value
