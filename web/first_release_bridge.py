"""Precomputed beta bridge for the audited VM app; no model or collector reads.

This file is installed beside the existing app. It depends only on the web
runtime and the immutable publisher's JSON protocol, not its research modules.
"""
import json
import os
from pathlib import Path
import time
from urllib.parse import parse_qs

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import HTMLResponse, JSONResponse, FileResponse, Response

ROSTER=frozenset(("arg:Ceibo Flower","can:Crocus","cay:Banana Orchid","haw:Orchid",
 "jap:Cherry Blossom","mex:Dahlia","mex:Jaguar Plushie","swi:Edelweiss",
 "uae:Tribulus Omanense","uni:Heather"))
ASSETS=Path(__file__).with_name("first_release_assets")
UI_REVISION="travel-windows-v1"


def read_board(*,now=None,path=None):
    now=int(time.time()) if now is None else now
    p=Path(path or os.environ.get("TORN_FREN_FIRST_RELEASE_SNAPSHOT","/var/lib/torn-fren-live-beta/latest.json"))
    if not p.is_file() or p.stat().st_size>8*1024*1024:
        raise ValueError("beta snapshot unavailable")
    s=json.loads(p.read_text())
    if set(s.get("items",{}))!=ROSTER or s.get("schema_version")!=1:
        raise ValueError("incomplete beta snapshot")
    if type(s.get("published_epoch")) is not int or s["published_epoch"]>now+15:
        raise ValueError("invalid beta publication clock")
    stale=now>s["valid_until_epoch"]
    rows=[]
    for key,r in sorted(s["items"].items()):
        d=dict(r.get("decision") or {})
        if stale:
            d["status"]="STALE_DATA"
            for f in ("estimated_departure_epoch","estimated_arrival_epoch","departure_countdown_seconds"):
                d[f]=None
        rows.append({"item_key":key,"decision":d,"forecast":r.get("forecast"),
            "live":s.get("live_metrics",{}).get(key,{}),
            "country_clock":r.get("country_clock"),
            "valid_until_epoch":s["valid_until_epoch"],
            "source_heartbeat_epoch":r.get("source_heartbeat_epoch"),
            "model_sha":s["model_sha"]})
    return {"status":"STALE_DATA" if stale else "LIVE_BETA","rows":rows,"ui_revision":UI_REVISION,
            "asof_epoch":s["asof_epoch"],"published_epoch":s["published_epoch"],
            "valid_until_epoch":s["valid_until_epoch"],"model_sha":s["model_sha"],
            "source_heartbeat_epoch":s["source_heartbeat_epoch"],
            "publisher_sha":s.get("publisher_sha",s["model_sha"]),
            "source_refresh":s.get("source_refresh"),
            "recent_publications":s.get("recent_publications",[]),
            "stock_success_rule":s["stock_success_rule"],"flight_profile":s["flight_profile"]}


def attach_history(payload,board):
    key=payload.get("country","")+":"+payload.get("item","")
    row=next((r for r in board["rows"] if r["item_key"]==key),None)
    a=payload.setdefault("analysis",{})
    a["first_release"] = row or {"item_key":key,"status":"ITEM_UNDER_REVIEW",
                                  "decision":{},"live":{}}
    # Never mix old V2 accuracy or archived overlays into the new beta.
    a["baseline_prediction"]=None; a["forecast_history"]=[]
    a["prediction"]=None
    a["prediction_v2"]={"status":"LIVE_BETA" if row else "ITEM_UNDER_REVIEW",
        "display_prediction":None,"predictions":[],"model_evidence_tier":"live beta",
        "arrival_success_rate":None,"recent10_arrival_success_rate":None,
        "note":"Live beta: stock above 30 at calculated arrival. Results start with this release." if row else "This item's model is under review; beta departure advice is not enabled."}
    a["prediction_v2_stale"]=board["status"]!="LIVE_BETA"
    if not row:
        return payload
    d=row["decision"]; f=row["forecast"] or {}; metrics=row["live"]
    dep=d.get("estimated_departure_epoch")
    if dep is None:
        a["prediction_v2"]["status"]=d.get("status","UNAVAILABLE")
        return payload
    index=d.get("selected_restock_event_index")
    event=next((e for e in d.get("forecast_events",[]) if e["index"]==index),None)
    if index==0:
        # Calculation time is not a restock. Keep the old chart's reference
        # timestamp usable without inventing an observed opening at issue time.
        center=d["estimated_arrival_epoch"]
        restock_center=restock_lo=restock_hi=None
        end=(f.get("current_stock_window") or {}).get("predicted_stock_below_30_epoch")
    else:
        center=restock_center=event["predicted_restock_epoch"]
        restock_lo=event["restock_early_epoch"]; restock_hi=event["restock_late_epoch"]
        end=event["predicted_stock_below_30_epoch"]
    deadline=d["estimated_departure_deadline_epoch"]; flight=d["player_flight_seconds"]
    arrival_start=dep+flight; arrival_end=deadline+flight
    prediction={"first_release":True,"estimate_timestamp":center,
        "opportunity_kind":"CURRENT_STOCK" if index==0 else "PREDICTED_STOCK_WINDOW",
        "estimate_kind":"ARRIVAL_REFERENCE" if index==0 else "RESTOCK_ESTIMATE",
        "restock_estimate_timestamp":restock_center,
        "restock_window_start_timestamp":restock_lo,"restock_window_end_timestamp":restock_hi,
        "departure_window_start_timestamp":dep,"departure_window_end_timestamp":deadline,
        "arrival_window_start_timestamp":arrival_start,"arrival_window_end_timestamp":arrival_end,
        "valid_until_epoch":row["valid_until_epoch"],
        # The graph must extend into the future far enough to display both
        # travel windows, rather than stopping at a past restock reference.
        "window_start_timestamp":arrival_start,"window_end_timestamp":arrival_end,
        "target_depletion_timestamp":end,"prediction_number":index,
        "projected":index>1,"recommended_arrival_timestamp":d["estimated_arrival_epoch"],
        "departure_epoch":dep,"departure_deadline_epoch":d["estimated_departure_deadline_epoch"],
        "flight_seconds":d["player_flight_seconds"],"travel_reliability":"beta",
        "model_name":d["timing_model_generation"].upper()+" "+d["timing_model_config"],
        "note":"Earliest reachable opportunity · live beta · stock >30"}
    a["prediction"]=prediction
    a["prediction_v2"].update(display_prediction=prediction,predictions=[prediction],
        model_name=prediction["model_name"],recent10_arrival_success_rate=metrics.get("success_fraction"))
    return payload


def install_first_release(app):
    class BetaMiddleware(BaseHTTPMiddleware):
        async def dispatch(self,request,call_next):
            path=request.url.path
            if path.startswith("/first-release-assets/"):
                name=path.rsplit("/",1)[-1]
                if name in ("beta.js","beta.css"):
                    return FileResponse(ASSETS/name,headers={"Cache-Control":"no-cache"})
                return Response(status_code=404)
            if path in ("/experimental","/travel-decisions"):
                return FileResponse(ASSETS/"board.html",media_type="text/html",headers={"Cache-Control":"no-store"})
            if path in ("/api/first-release","/api/travel-decisions","/api/experimental/v41/predictions"):
                try:
                    board=read_board()
                    return JSONResponse(board,headers={"Cache-Control":"no-store"})
                except (OSError,ValueError,KeyError):
                    return JSONResponse({"status":"BETA_FEED_UNAVAILABLE","rows":[]},status_code=503)
            response=await call_next(request)
            if path=="/api/history" and response.status_code==200:
                raw=b"".join([chunk async for chunk in response.body_iterator])
                try:
                    payload=json.loads(raw)
                    try: board=read_board()
                    except (OSError,ValueError,KeyError):
                        board={"status":"BETA_FEED_UNAVAILABLE","rows":[]}
                    return JSONResponse(attach_history(payload,board),headers={"Cache-Control":"no-store"})
                except (ValueError,TypeError,KeyError):
                    return Response(raw,status_code=502,media_type="application/json")
            if path=="/" and response.status_code==200 and "text/html" in response.headers.get("content-type",""):
                raw=b"".join([chunk async for chunk in response.body_iterator])
                tag=b'<link rel="stylesheet" href="/first-release-assets/beta.css"><script src="/first-release-assets/beta.js"></script>'
                return HTMLResponse(raw.replace(b"</body>",tag+b"</body>"),headers={"Cache-Control":"no-store"})
            return response
    app.add_middleware(BetaMiddleware)
