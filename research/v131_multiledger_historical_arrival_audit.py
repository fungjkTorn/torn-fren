"""V131: read-only historical-arrival audit of OLD V75 and NEW V128.

V75 candidates were actually issued before V128 existed. Select FIRST
issuance per item UTC hour, *including abstentions*, to avoid counting
dozens of adjacent replans as independent restocks. Apply V76 validity
contract, then V88 successful poll bracket >=30 at predicted arrival and
matched leave-now counterfactual. Preserve unknown source, pending,
unverified country-feed, and absence of actual gameplay flights.

V128: reuse frozen V129 scoring, but do NOT imply any old one-batch data is
mature when it isn't. Never retrain, backfill, or issue new predictions.

Optional V81 selector and V84 Japan forward research ledgers are inventoried
only: their distinct model families require dedicated matched study.
All SQLite opened mode=ro, PRAGMA query_only, and no model/website/service
edits. Limited to 1-7 days and bounded candidate rows.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections import Counter,defaultdict
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path

from research.v76_forward_research_report import V75,SOURCE,ro,eligible
from research.v88_poll_state_forward_report import observation
from research.plushie_champions.common import TRAVEL_SECONDS
from research.v60_private_snapshot_probe import approved_collector_source
from research.v128_full24_earliest_shadow import SIDECAR,exact_roster
from research.v129_full24_forward_report import audit as v128_audit

MAX_DAYS=7
MAX_RAW=120000
MAX_HOURLY=4200
SHOW_EVENTS=8
OPTIONAL=(
    ("v72_older_pilot",Path("/var/lib/torn-fren-v38/v72_private_predictions.db"),"v42_candidate_decisions","computed_at"),
    ("v81_lion_panda",Path("/home/ubuntu/torn-fren-private-models/v81_pair_forward.db"),"pair_issued_decisions","issued_at"),
    ("v84_japan_xanax",Path("/home/ubuntu/torn-fren-private-models/v84_japan_forward.db"),"japan_forward_decisions","issued_at"),
)


def epoch_utc(t):
    if t is None:return None
    return datetime.fromtimestamp(int(t),tz=timezone.utc).isoformat(timespec="seconds")


def opening(path):
    p=Path(path).resolve(strict=True)
    if not p.is_file():raise ValueError("missing ledger file")
    con=sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=15)
    con.execute("PRAGMA query_only=ON")
    con.row_factory=sqlite3.Row
    return con


def inventory(*,asof,lookback_days=MAX_DAYS):
    out={}
    for name,path,table,tcol in OPTIONAL:
        if not path.exists():
            out[name]={"status":"NOT_FOUND_AT_KNOWN_LOCATION"}
            continue
        try:
            with closing(opening(path)) as c:
                total=int(c.execute("SELECT COUNT(*) FROM "+table).fetchone()[0])
                recent=int(c.execute(
                    "SELECT COUNT(*) FROM "+table+" WHERE "+tcol+">=?",
                    (asof-lookback_days*86400,)).fetchone()[0])
                latest=c.execute("SELECT MAX("+tcol+") FROM "+table).fetchone()[0]
            out[name]={"status":"AVAILABLE","rows_total":total,
                       "rows_last_"+str(lookback_days)+"d":recent,
                       "last_issue_utc":epoch_utc(latest)}
        except (ValueError,sqlite3.Error,OSError) as ex:
            out[name]={"status":"UNREADABLE_OR_DIFFERENT_SCHEMA",
                       "error_type":type(ex).__name__}
    return out


def summarize(c):
    n=c["item_hours"]
    both=c["both_scorable"]
    return {
        "first_item_UTC_hourly_starts":n,
        "valid_departure_proposals":c["proposals"],
        "no_valid_departure_or_abstention":c["no_valid"],
        "old_model_arrival_stock_at_least_30":c["model_hit"],
        "old_model_arrival_stock_below_30":c["model_miss"],
        "old_model_arrival_unknown_or_pending":c["model_unknown"],
        "old_model_arrivals_still_pending":c["model_pending"],
        "matched_flight_outcomes":both,
        "matched_both_stocked":c["both_hit"],
        "matched_only_old_model_stocked":c["model_only"],
        "matched_only_leave_now_stocked":c["now_only"],
        "matched_both_below_30":c["both_miss"],
        "matched_model_stocked_fraction":round(
            (c["both_hit"]+c["model_only"])/both,4) if both else None,
        "matched_leave_now_stocked_fraction":round(
            (c["both_hit"]+c["now_only"])/both,4) if both else None,
        "model_minus_now_only_known_pairs":c["model_only"]-c["now_only"],
        "all_starts_observed_model_stocked_lower_bound":round(
            c["model_hit"]/n,4) if n else None,
    }


def tally(table,row):
    for c in (table[row["item_key"]],):
        c["item_hours"]+=1


def v75_report(*,ledger=V75,stock=SOURCE,asof,days=3,
               max_raw=MAX_RAW,max_hourly=MAX_HOURLY,
               scorer=observation):
    if not 1<=days<=MAX_DAYS or not 1<=max_raw<=MAX_RAW:
        raise ValueError("invalid historical scope")
    if Path(ledger).resolve(strict=True)==Path(stock).resolve(strict=True):
        raise ValueError("read-only ledgers must be separate")
    with closing(ro(ledger)) as issued_db:
        n=int(issued_db.execute(
            "SELECT COUNT(*) FROM v42_candidate_decisions"
            " WHERE computed_at BETWEEN ? AND ?",
            (asof-days*86400,asof)).fetchone()[0])
        if n>max_raw:raise ValueError(
            "legacy raw history exceeds bounded cap; reduce days")
        rows=issued_db.execute(
            """SELECT item_key,computed_at,stock_as_of,status,valid_until,
                      departure,arrival,actual_player_departure,
                      model_family,model_config
               FROM v42_candidate_decisions
               WHERE computed_at BETWEEN ? AND ?
               ORDER BY computed_at,id""",
            (asof-days*86400,asof)).fetchall()
    if len(rows)!=n:
        raise ValueError("nonrepeatable raw legacy count")
    # At most one *first* as-issued recommendation/abstention per UTC hour;
    # fixed before accessing any later observation.
    first={}
    for r in rows:
        key=(r["item_key"],int(r["computed_at"])//3600)
        first.setdefault(key,r)
        if len(first)>max_hourly:
            raise ValueError("too many first-hour observations")
    roster=set(exact_roster())
    counters=defaultdict(Counter)
    all_count=Counter()
    reason=Counter()
    statuses=Counter()
    most_recent=[]
    with closing(ro(stock)) as collector:
        for r in first.values():
            key=r["item_key"]
            if key not in roster:
                reason["OUTSIDE_CURRENT_EXACT_24_ROSTER"]+=1
                continue
            counters[key]["item_hours"]+=1
            all_count["item_hours"]+=1
            statuses[str(r["status"])]+=1
            if not eligible(r):
                for c in (counters[key],all_count):
                    c["no_valid"]+=1
                reason["NO_VALID_DEPARTURE_"+str(r["status"])]+=1
                continue
            country,item=key.split(":",1)
            departure=int(r["departure"])
            arrival=int(r["arrival"])
            baseline=int(r["computed_at"])+TRAVEL_SECONDS[country]
            status,hit,metadata=scorer(
                collector,country,item,arrival,asof)
            baseline_status,baseline_hit,_=scorer(
                collector,country,item,baseline,asof)
            for c in (counters[key],all_count):
                c["proposals"]+=1
                if hit is True:c["model_hit"]+=1
                elif hit is False:c["model_miss"]+=1
                else:c["model_unknown"]+=1
                if status=="PENDING":c["model_pending"]+=1
                if hit is not None and baseline_hit is not None:
                    c["both_scorable"]+=1
                    if hit and baseline_hit:c["both_hit"]+=1
                    elif hit:c["model_only"]+=1
                    elif baseline_hit:c["now_only"]+=1
                    else:c["both_miss"]+=1
            reason["MODEL_"+status]+=1
            reason["LEAVE_NOW_"+baseline_status]+=1
            most_recent.append({
                "item_key":key,
                "issued_utc":epoch_utc(r["computed_at"]),
                "model_family":r["model_family"],
                "wait_minutes":round((departure-int(r["computed_at"]))/60,2),
                "predicted_arrival_utc":epoch_utc(arrival),
                "arrived_stock_proxy":status,
                "observed_bracketing_stock_quantities":(
                    [metadata["pre_quantity"],metadata["post_quantity"]]
                    if "pre_quantity" in metadata and
                       "post_quantity" in metadata else None),
                "leave_now_stock_proxy":baseline_status,
                "country_update_freshness_verified":False,
            })
    most_recent.sort(key=lambda x:x["issued_utc"],reverse=True)
    return {
        "status":"V131_OLDER_V75_24_ROSTER_FIRST_ISSUE_HOURLY_ARRIVAL_AUDIT",
        "days":days,
        "raw_as_issued_forecasts_in_scope":n,
        "unique_item_UTC_hourly_first_issues_in_scope":len(first),
        "analysis_UTC":epoch_utc(asof),
        "summary":summarize(all_count),
        "per_item":{k:summarize(counters[k]) for k in sorted(roster)},
        "original_issue_status_counts":dict(statuses),
        "missing_and_proxy_reason_counts":dict(reason),
        "recent_paired_arrival_observations":most_recent[:SHOW_EVENTS],
        "global_collector_poll_cannot_prove_country_feed_freshness":True,
        "not_independent_restock_cycles":True,
        "actual_gameplay_or_purchases_verified":False,
        "no_fitted_models_or_revisions":True,
    }


def v128_report(*,asof,days=3):
    if not SIDECAR.exists():
        return {"status":"NEW_V128_PRIVATE_LEDGER_MISSING"}
    output=v128_audit(now=asof,days=min(days,3))
    return {
        "status":output["status"],
        "raw_five_minute_rows":output["raw_five_minute_issue_rows"],
        "first_issued_item_hour_cohorts":output["first_item_UTC_hourly_cohorts"],
        "summary":output["overall"],
        "per_item":output["per_item"],
        "matched_outcome_requires_departure_and_arrival_maturity":True,
        "uncalibrated_stock_proxy_not_gameplay":True,
    }


def full_audit(*,asof=None,days=3,legacy=V75,stock=SOURCE):
    asof=int(time.time() if asof is None else asof)
    if not approved_collector_source(stock):
        raise ValueError("unapproved source")
    result={"status":"V131_MULTILEDGER_HISTORICAL_ARRIVAL_CHECK",
            "read_only":True,"analysis_UTC":epoch_utc(asof),
            "all_24_roster_count":len(exact_roster())}
    result["older_sidecar_inventory"]=inventory(asof=asof)
    if Path(legacy).exists():
        result["old_V75"]=v75_report(
            ledger=legacy,stock=stock,asof=asof,days=days)
    else:
        result["old_V75"]={"status":"OLD_V75_LEDGER_NOT_FOUND"}
    result["new_V128"]=v128_report(asof=asof,days=days)
    result["verified_gameplay_flights_or_purchases"]=False
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days",type=int,choices=range(1,8),default=3)
    p.add_argument("--json",action="store_true")
    args=p.parse_args()
    out=full_audit(days=args.days)
    if args.json:
        print(json.dumps(out,sort_keys=True))
        return
    print("===== VM AS-ISSUED STOCK-AT-ARRIVAL AUDIT =====")
    print("As of UTC:",out["analysis_UTC"])
    print("Older sidecars:",json.dumps(
        out["older_sidecar_inventory"],sort_keys=True))
    old=out["old_V75"]
    print("OLDER V75 STATUS:",old["status"])
    if "summary" in old:
        print("Older raw issue rows:",old["raw_as_issued_forecasts_in_scope"])
        print("Older first-hour cohorts:",
              old["unique_item_UTC_hourly_first_issues_in_scope"])
        print("OLDER V75 MODEL VS LEAVE NOW:",
              json.dumps(old["summary"],sort_keys=True))
        print("OLD V75 EACH ITEM:",
              json.dumps(old["per_item"],sort_keys=True))
        print("OBSERVATION UNKNOWN/PENDING:",
              json.dumps(old["missing_and_proxy_reason_counts"],sort_keys=True))
        print("RECENT STOCK AT ACTUAL PREDICTED ARRIVALS:",
              json.dumps(old["recent_paired_arrival_observations"],sort_keys=True))
    new=out["new_V128"]
    print("NEW V128 STATUS:",new["status"])
    if "summary" in new:
        print("NEW V128 recorded rows:",new["raw_five_minute_rows"])
        print("NEW V128 first-hour item cohorts:",
              new["first_issued_item_hour_cohorts"])
        print("NEW V128 MODEL VS LEAVE NOW:",
              json.dumps(new["summary"],sort_keys=True))
        print("NEW V128 PER ITEM:",
              json.dumps(new["per_item"],sort_keys=True))
    print("CAUTION: stock >=30 proxy, not verified per-country stock freshness "
          "or actual gameplay purchases.")
    print("READ ONLY: no collector, model, website, or sidecar changes.")


if __name__=="__main__":
    main()
