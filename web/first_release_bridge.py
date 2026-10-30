"""Precomputed beta bridge for the audited VM app; no model or collector reads.

This file is installed beside the existing app. It depends only on the web
runtime and the immutable publisher's JSON protocol, not its research modules.
"""
import json
import bisect
import sqlite3
import statistics
from contextlib import closing
from functools import lru_cache
import os
from pathlib import Path
import time
from urllib.parse import parse_qs

from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import HTMLResponse, JSONResponse, FileResponse, Response

ROSTER=frozenset(("arg:Ceibo Flower","can:Crocus","cay:Banana Orchid","haw:Orchid",
 "jap:Cherry Blossom","mex:Dahlia","mex:Jaguar Plushie","swi:Edelweiss",
 "uae:Tribulus Omanense","uni:Heather"))
CHALLENGER_ROSTER=frozenset(('arg:Monkey Plushie','can:Wolverine Plushie','cay:Stingray Plushie',
    'chi:Peony','sou:African Violet','sou:Lion Plushie'))
ASSETS=Path(__file__).with_name("first_release_assets")
UI_REVISION="forward-beta-six-v1"


def _read_single_board(*,now=None,path=None,roster=ROSTER):
    now=int(time.time()) if now is None else now
    p=Path(path or os.environ.get("TORN_FREN_FIRST_RELEASE_SNAPSHOT","/var/lib/torn-fren-live-beta/latest.json"))
    if not p.is_file() or p.stat().st_size>8*1024*1024:
        raise ValueError("beta snapshot unavailable")
    s=json.loads(p.read_text())
    if set(s.get("items",{}))!=roster or s.get("schema_version")!=1:
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


def read_board(*,now=None,path=None,challenger_path=None):
    board=_read_single_board(now=now,path=path)
    extra=Path(challenger_path or os.environ.get('TORN_FREN_CHALLENGER_SNAPSHOT','/var/lib/torn-fren-live-beta/challengers/latest.json'))
    board['cohorts']={'incumbents':{'status':board['status'],'items':len(board['rows']),'model_sha':board['model_sha']}}
    # Default original-ten fixtures and installations remain valid until a
    # separately verified challenger publisher is installed.
    if not extra.exists():return board
    try:
        added=_read_single_board(now=now,path=extra,roster=CHALLENGER_ROSTER)
    except (OSError,ValueError,KeyError,TypeError):
        board['cohorts']['challengers']={'status':'UNAVAILABLE','items':0}
        return board
    if added['stock_success_rule']!=board['stock_success_rule'] or added['flight_profile']!=board['flight_profile']:
        board['cohorts']['challengers']={'status':'INCOMPATIBLE','items':0}
        return board
    for row in board['rows']:row['cohort']='incumbents'
    for row in added['rows']:row['cohort']='challengers'
    board['rows']=sorted(board['rows']+added['rows'],key=lambda r:r['item_key'])
    board['cohorts']['challengers']={'status':added['status'],'items':len(added['rows']),
        'model_sha':added['model_sha'],'published_epoch':added['published_epoch']}
    return board


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


# Historical descriptive statistics are cached separately from forecasting.
# No fitting, collector writes or old V2 analysis is enabled by this endpoint.
@lru_cache(maxsize=32)
def _history_summary_cached(path,country,item,bucket):
    cutoff=int(time.time());deadline=time.monotonic()+2
    with closing(sqlite3.connect(Path(path).resolve(strict=True).as_uri()+'?mode=ro',uri=True,timeout=2)) as db:
        db.execute('PRAGMA query_only=ON');db.execute('PRAGMA temp_store=MEMORY')
        db.set_progress_handler(lambda:time.monotonic()>deadline,10000);db.execute('BEGIN')
        rows=db.execute('''SELECT timestamp,quantity,source FROM stock_history
            WHERE country=? AND lower(item_name)=lower(?) AND timestamp<=?
            ORDER BY timestamp,id LIMIT 50001''',(country,item,cutoff)).fetchall()
        if len(rows)>50000:raise ValueError('bounded historical sample exceeded')
        if len(rows)<2:return {'status':'UNAVAILABLE','reason':'No exported historical sample for this item.'}
        gaps=db.execute('''SELECT start_timestamp,end_timestamp FROM collection_gaps
            WHERE start_timestamp<=? AND COALESCE(end_timestamp,9223372036854775807)>=?
            ORDER BY start_timestamp''',(cutoff,rows[0][0])).fetchall()
        hb=db.execute("SELECT MAX(timestamp) FROM poll_heartbeats WHERE success=1 AND mode='poll-cycle' AND timestamp<=?",(cutoff,)).fetchone()[0]
    starts=[];ends=[];maximum=0
    for start,end in gaps:
        starts.append(start);maximum=max(maximum,min(cutoff,end if end is not None else cutoff));ends.append(maximum)
    def gap_between(a,b):
        index=bisect.bisect_right(starts,b)-1
        return index>=0 and ends[index]>=a
    high_durations=[];low_durations=[];onset=None;last_open=None;last_zero=None;uncertain=0
    previous=None;peak=max(rows,key=lambda r:r[1])
    for row in rows:
        stamp,quantity,provider=row
        if previous is not None:
            t0,q0,p0=previous
            dirty=stamp<=t0 or gap_between(t0,stamp)
            conflict=provider!=p0 and (quantity>30)!=(q0>30)
            if dirty or conflict:
                onset=None;uncertain+=1
            else:
                if p0==provider and q0>0 and quantity==0:last_zero=stamp
                if (q0>30)!=(quantity>30):
                    if onset is not None:
                        (high_durations if q0>30 else low_durations).append(stamp-onset)
                    if quantity>30:last_open=stamp
                    onset=stamp
        previous=row
    average=lambda values:round(statistics.mean(values)) if values else None
    median=lambda values:round(statistics.median(values)) if values else None
    return {'status':'AVAILABLE','calculated_epoch':cutoff,'source_heartbeat_epoch':hb,
        'sample_start_epoch':rows[0][0],'sample_end_epoch':rows[-1][0],'sample_rows':len(rows),
        'last_restock_timestamp':last_open,'last_depletion_timestamp':last_zero,
        'last_peak_quantity':peak[1],'last_peak_timestamp':peak[0],
        'avg_stocked_seconds':average(high_durations),'median_stocked_seconds':median(high_durations),
        'avg_unstocked_seconds':average(low_durations),'median_unstocked_seconds':median(low_durations),
        'completed_stock_windows':len(high_durations),'uncertain_boundaries':uncertain,
        'stocked_threshold':'>30','depletion_threshold':'=0','forecast_accuracy_claimed':False,'source_read_only':True}


def read_history_summary(country,item,*,path=None):
    if country not in {'arg','can','cay','haw','jap','mex','swi','uae','uni','chi','sou'} or not item or len(item)>120 or '\x00' in item:
        raise ValueError('invalid item selection')
    source=path or (os.environ.get('TORN_FREN_CHALLENGER_HISTORY','/var/lib/torn-fren-live-beta/challengers/stock_history.sqlite') if country+':'+item in CHALLENGER_ROSTER else os.environ.get('TORN_FREN_HISTORY_SUMMARY_SOURCE','/var/lib/torn-fren-research/stock_history_forward.db'))
    return dict(_history_summary_cached(str(source),country,item,int(time.time())//300))


def install_first_release(app):
    class BetaMiddleware(BaseHTTPMiddleware):
        async def dispatch(self,request,call_next):
            path=request.url.path
            if path=="/api/first-release/history-summary":
                try:
                    summary=await run_in_threadpool(read_history_summary,request.query_params.get('country',''),request.query_params.get('item',''))
                    return JSONResponse(summary,headers={"Cache-Control":"no-store"})
                except (OSError,ValueError,sqlite3.Error):
                    return JSONResponse({"status":"UNAVAILABLE","reason":"Historical sample is unavailable; live stock and forecasts are separate."},headers={"Cache-Control":"no-store"})
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
