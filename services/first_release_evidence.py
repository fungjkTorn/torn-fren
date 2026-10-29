"""Append-only beta forecast log and poll-backed arrival evidence (>30)."""
from __future__ import annotations

import bisect
from copy import deepcopy
from collections import Counter
import json
from pathlib import Path
import sqlite3


def connect(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("refuse symlinked forecast ledger")
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
      CREATE TABLE IF NOT EXISTS issues(
        item TEXT NOT NULL, issued INTEGER NOT NULL, model_sha TEXT NOT NULL,
        payload TEXT NOT NULL, PRIMARY KEY(item,issued));
      CREATE TABLE IF NOT EXISTS outcomes(
        item TEXT NOT NULL, issued INTEGER NOT NULL, cutoff INTEGER NOT NULL,
        payload TEXT NOT NULL, PRIMARY KEY(item,issued,cutoff),
        FOREIGN KEY(item,issued) REFERENCES issues(item,issued));
      CREATE TABLE IF NOT EXISTS publications(
        issued INTEGER PRIMARY KEY, published INTEGER NOT NULL, snapshot_sha TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS target_links(
        item TEXT NOT NULL, issued INTEGER NOT NULL, payload TEXT NOT NULL,
        PRIMARY KEY(item,issued), FOREIGN KEY(item,issued) REFERENCES issues(item,issued));
      CREATE TRIGGER IF NOT EXISTS immutable_targets_update BEFORE UPDATE ON target_links
        BEGIN SELECT RAISE(ABORT,'observed target links are immutable'); END;
      CREATE TRIGGER IF NOT EXISTS immutable_targets_delete BEFORE DELETE ON target_links
        BEGIN SELECT RAISE(ABORT,'observed target links are immutable'); END;
      CREATE TRIGGER IF NOT EXISTS immutable_issues_update BEFORE UPDATE ON issues
        BEGIN SELECT RAISE(ABORT,'issued forecasts are immutable'); END;
      CREATE TRIGGER IF NOT EXISTS immutable_issues_delete BEFORE DELETE ON issues
        BEGIN SELECT RAISE(ABORT,'issued forecasts are immutable'); END;
      CREATE TRIGGER IF NOT EXISTS immutable_outcomes_update BEFORE UPDATE ON outcomes
        BEGIN SELECT RAISE(ABORT,'outcomes are append-only'); END;
      CREATE TRIGGER IF NOT EXISTS immutable_outcomes_delete BEFORE DELETE ON outcomes
        BEGIN SELECT RAISE(ABORT,'outcomes are append-only'); END;
    """)
    from services.simulated_trip_evidence import initialize
    initialize(db)
    return db


def record(db, row, *, model_sha):
    key = row["item_key"]
    issued = row["asof_epoch"]
    # The public feed retains the full calendar; the permanent log retains
    # the complete selected prediction, not 64 duplicated future windows on
    # every refresh. This keeps evidence growth bounded without losing the
    # departure/arrival, target bounds or depletion forecast being evaluated.
    archived = deepcopy(row)
    d = archived.get("decision") or {}
    selected = d.get("selected_restock_event_index")
    if "forecast_events" in d:
        d["forecast_events"] = [e for e in d["forecast_events"] if e.get("index") == selected]
    f = archived.get("forecast") or {}
    for field in ("restock_events", "true_restock_events"):
        if field in f:
            f[field] = [e for e in f[field] if e.get("event_index") == selected]
    archived["evidence_format"] = "SELECTED_OPPORTUNITY_AND_ISSUE_PROVENANCE"
    payload = json.dumps(archived, sort_keys=True, separators=(",", ":"))
    old = db.execute("SELECT model_sha,payload FROM issues WHERE item=? AND issued=?",
                     (key, issued)).fetchone()
    if old:
        if tuple(old) != (model_sha, payload):
            raise ValueError("cannot replace an issued forecast")
        return
    db.execute("INSERT INTO issues VALUES(?,?,?,?)", (key, issued, model_sha, payload))


def grade(arrival, rows, polls, gaps, *, cutoff):
    """Use observations bracketing actual landing, not a post-arrival grace.

    Rows are change-only stock states (epoch, quantity, provider). Successful
    poll heartbeats corroborate carried-forward values. Country freshness is
    reported independently by the publisher; global polls cannot prove it.
    """
    if cutoff < arrival + 180:
        return {"status": "PENDING", "reason": "ARRIVAL_NOT_MATURE"}
    i = bisect.bisect_right(polls, arrival) - 1
    j = bisect.bisect_left(polls, arrival)
    if i < 0 or j >= len(polls):
        return {"status": "UNKNOWN", "reason": "NO_POLL_BRACKET"}
    before, after = polls[i], polls[j]
    if arrival-before > 180 or after-arrival > 180:
        return {"status": "UNKNOWN", "reason": "SPARSE_POLL_BRACKET"}
    if any(a <= after and (b is None or b >= before) for a, b in gaps):
        return {"status": "UNKNOWN", "reason": "COLLECTION_GAP"}
    times = [r[0] for r in rows]
    a = bisect.bisect_right(times, before)-1
    b = bisect.bisect_right(times, after)-1
    if a < 0 or b < 0 or before-times[a] > 86400:
        return {"status": "UNKNOWN", "reason": "NO_RECENT_ITEM_STATE"}
    segment = rows[a:b+1]
    if len({r[2] for r in segment}) != 1:
        return {"status": "UNKNOWN", "reason": "PROVIDER_SWITCH"}
    if len({r[1] > 30 for r in segment}) != 1:
        return {"status": "UNKNOWN", "reason": "THRESHOLD_TRANSITION_IN_BRACKET"}
    return {"status": "SUCCESS" if segment[0][1] > 30 else "FAILURE",
            "reason": "POLL_BACKED_STOCK_AT_LANDING", "pre_poll": before,
            "post_poll": after, "pre_quantity": rows[a][1],
            "post_quantity": rows[b][1], "provider": rows[a][2]}


def openings(rows, gaps):
    """Observed buying-window openings, with no inferred gap/provider crossing."""
    out = []
    for a, b in zip(rows, rows[1:]):
        if a[1] <= 30 < b[1] and a[2] == b[2] and b[0] > a[0]:
            if not any(lo <= b[0] and (hi is None or hi >= a[0]) for lo, hi in gaps):
                out.append({"epoch": b[0], "earliest_epoch": a[0], "provider": b[2]})
    return out


class TargetIndex:
    """Index actual opening ordinals once, not once per forecast revision."""
    def __init__(self, rows, gaps):
        self.history_start = rows[0][0] if rows else None
        self.actual = openings(rows, gaps)
        self.times = [r["epoch"] for r in self.actual]
        # Agreement on availability preserves a buying window. Only a
        # cross-provider threshold contradiction makes its identity ambiguous.
        self.switches = [b[0] for a,b in zip(rows,rows[1:])
            if a[2] != b[2] and (a[1] > 30) != (b[1] > 30)]
        usable = sorted((a, b if b is not None else 2**63-1) for a,b in gaps)
        self.gap_starts = [a for a,b in usable]
        self.gap_ends = []
        maximum = -1
        for a,b in usable:
            maximum = max(maximum,b)
            self.gap_ends.append(maximum)

    def target(self, issue):
        d = issue.get("decision") or {}
        ordinal = d.get("selected_restock_event_index")
        issued = issue["asof_epoch"]
        if self.history_start is None or issued < self.history_start:
            return None
        if type(ordinal) is not int or ordinal < 0:
            return None
        before = bisect.bisect_right(self.times, issued)
        idx = before-1 if ordinal == 0 else before+ordinal-1
        if idx < 0 or idx >= len(self.actual):
            return None
        selected = self.actual[idx]
        lo, hi = sorted((issued,selected["epoch"]))
        g = bisect.bisect_right(self.gap_starts,hi)-1
        if g >= 0 and self.gap_ends[g] >= lo:
            return None
        a = bisect.bisect_right(self.switches,lo)
        if a < len(self.switches) and self.switches[a] <= hi:
            return None
        return selected


def target_for_issue(issue, rows, gaps, *, index=None):
    """Observed ordinal matching, never nearest-to-predicted-time matching."""
    return (index or TargetIndex(rows,gaps)).target(issue)


def score(db, source, *, cutoff, model_sha):
    """Score saved forecasts; never rerun a model using outcome data."""
    pending = db.execute("""SELECT i.item,i.issued,i.payload FROM issues i
        WHERE i.model_sha=? AND i.issued IN (SELECT issued FROM publications) AND NOT EXISTS (
          SELECT 1 FROM outcomes o WHERE o.item=i.item AND o.issued=i.issued
          AND json_extract(o.payload,'$.status') IN ('SUCCESS','FAILURE','UNKNOWN'))
        ORDER BY i.issued LIMIT 50000""", (model_sha,)).fetchall()
    polls = [r[0] for r in source.execute("SELECT timestamp FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1 AND timestamp<=? ORDER BY timestamp", (cutoff,))]
    gaps = source.execute("SELECT start_timestamp,end_timestamp FROM collection_gaps WHERE start_timestamp<=? ORDER BY start_timestamp", (cutoff,)).fetchall()
    histories = {}; indexes = {}
    for entry in pending:
        key = entry["item"]
        issue = json.loads(entry["payload"])
        d = issue.get("decision") or {}
        arrival = d.get("estimated_arrival_epoch")
        if type(arrival) is not int:
            continue
        if key not in histories:
            country, item = key.split(":", 1)
            histories[key] = source.execute("SELECT timestamp,quantity,source FROM stock_history WHERE country=? AND lower(item_name)=lower(?) AND timestamp<=? ORDER BY timestamp,id", (country,item,cutoff)).fetchall()
        if key not in indexes:
            indexes[key] = TargetIndex(histories[key],gaps)
        evidence = grade(arrival, histories[key], polls, gaps, cutoff=cutoff)
        # Store explicit target timing where it is already observed. Later
        # matching can still be done from immutable issues and source records.
        target = target_for_issue(issue, histories[key], gaps, index=indexes[key])
        if target is not None:
            evidence.update(actual_opening=target,
                arrival_minus_opening_seconds=arrival-target["epoch"])
        db.execute("INSERT OR IGNORE INTO outcomes VALUES(?,?,?,?)", (
            key,entry["issued"],cutoff,json.dumps(evidence,sort_keys=True)))


def legacy_summary(db, source, *, item_key, model_sha, cutoff):
    """First published forecast per observed opportunity, never 5m rows as trips.

    Unmatched issues remain visible separately and do not create independent
    successes. Failure rows still retain their stock outcome even while target
    identity is unconfirmed. This is an observed-opportunity scorecard, not an
    estimate of the model's probability for the next flight.
    """
    country, name = item_key.split(":",1)
    rows = source.execute("SELECT timestamp,quantity,source FROM stock_history WHERE country=? AND lower(item_name)=lower(?) AND timestamp<=? ORDER BY timestamp,id", (country,name,cutoff)).fetchall()
    gaps = source.execute("SELECT start_timestamp,end_timestamp FROM collection_gaps WHERE start_timestamp<=?", (cutoff,)).fetchall()
    entries = db.execute("SELECT item,issued,payload FROM issues WHERE item=? AND model_sha=? AND issued IN (SELECT issued FROM publications) ORDER BY issued", (item_key,model_sha)).fetchall()
    index = TargetIndex(rows,gaps)
    grouped = {}
    unmatched = Counter()
    raw_outcomes = Counter()
    for entry in entries:
        issue = json.loads(entry["payload"])
        d = issue.get("decision") or {}
        if d.get("estimated_departure_epoch") is None:
            continue
        latest = db.execute("SELECT payload FROM outcomes WHERE item=? AND issued=? ORDER BY cutoff DESC LIMIT 1", (item_key,entry["issued"])).fetchone()
        evidence = json.loads(latest[0]) if latest else {"status":"PENDING"}
        raw_outcomes[evidence["status"]] += 1
        saved_target = db.execute("SELECT payload FROM target_links WHERE item=? AND issued=?",(item_key,entry["issued"])).fetchone()
        target = json.loads(saved_target[0]) if saved_target else target_for_issue(issue,rows,gaps,index=index)
        if target is None:
            unmatched[evidence["status"]] += 1
            continue
        if saved_target is None:
            db.execute("INSERT INTO target_links VALUES(?,?,?)",(item_key,entry["issued"],json.dumps(target,sort_keys=True)))
        # The first forecast remains the evaluation forecast even if a later
        # revision would have produced a better landing.
        grouped.setdefault(target["epoch"], {
            "issued_epoch":entry["issued"],
            "departure_epoch":d["estimated_departure_epoch"],
            "arrival_epoch":d["estimated_arrival_epoch"],
            "predicted_restock_epoch": next((e["predicted_restock_epoch"] for e in d.get("forecast_events",[]) if e["index"]==d.get("selected_restock_event_index")),None),
            "actual_opening":target, "outcome":evidence,
        })
    trips = sorted(grouped.values(),key=lambda r:r["departure_epoch"],reverse=True)[:10]
    counts = Counter(t["outcome"]["status"] for t in trips)
    known = counts["SUCCESS"]+counts["FAILURE"]
    # Do not advertise a percentage while failed/unknown unmatched forecasts
    # are excluded from the event denominator. Their raw counts stay visible.
    unmatched_misses = unmatched["FAILURE"]+unmatched["UNKNOWN"]
    start = entries[0]["issued"] if entries else cutoff
    start = max(start,index.history_start or cutoff)
    observed = [o["epoch"] for o in index.actual if o["epoch"] >= start]
    return {"label":"Last 10 observed forecast opportunities",
            "evidence_policy":"PROVIDER_CONTINUOUS_FIRST_ISSUE_V2",
            "matched_opportunities_total":len(grouped),
            "matched_success_fraction":counts["SUCCESS"]/known if known else None,
            "recorded_forecast_revisions":sum(raw_outcomes.values()),
            "unmatched_revision_total":sum(unmatched.values()),
            "rate_status":"WITHHELD_UNMATCHED_OUTCOMES" if unmatched_misses else "KNOWN_MATCHED_RESULTS" if known else "UNKNOWN_RESULTS" if counts['UNKNOWN'] else "AWAITING_ARRIVALS" if counts['PENDING'] else "AWAITING_WINDOW_MATCH" if raw_outcomes else "NO_RECORDED_OUTCOMES",
            "trips":trips,"successes":counts["SUCCESS"],"failures":counts["FAILURE"],
            "unknown":counts["UNKNOWN"],"pending":counts["PENDING"],
            "known":known,"success_fraction":counts["SUCCESS"]/known if known and not unmatched_misses else None,
            "unmatched_forecast_rows":dict(unmatched),"raw_forecast_row_outcomes":dict(raw_outcomes),
            "percentage_withheld_for_unmatched_misses":bool(unmatched_misses),
            "observed_opportunities_since_start":len(observed),
            "coverage_start_epoch":start,
            "observed_opportunities_without_matched_forecast":sum(t not in grouped for t in observed),
            "actual_player_trips_required":False,"historical_rates_included":False}


def summary(db,source,*,item_key,model_sha,cutoff):
    from services.simulated_trip_evidence import summary as simulated_summary
    return simulated_summary(db,source,item_key=item_key,model_sha=model_sha,cutoff=cutoff)
