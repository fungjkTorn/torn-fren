"""Prospective, immutable physical-restock/departure issue ledger and audit.

Research ONLY: issue from a genuinely fresh 24-item read-only event snapshot.
Preserve ALL physical event ordinals, even when a flight is impossible. Score
the first and chosen ordinal with independent poll-bracket evidence after
issuance. A simulated landing is not an observed player flight or purchase.
No source collector, website, production prediction, or specialist writes.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import json
import os
from pathlib import Path
import re
import sqlite3
import time

from research.build_travel_event_snapshot import prepare
from research.physical_restock_identity import match
from research.v88_poll_state_forward_report import observation
from services.travel_decision_contract_v166 import (
    STATUS_ACTIVE, STATUS_WAIT, build_item_travel_decision,
)

POLICY = "physical_event_first_asissued_v1"
SIDECAR_NAME = "physical_event_forward.db"
MAX_ROWS = 24000
MAX_ITEM_CHANGES = 100000
MAX_POLLS = 400000
MAX_DAYS = 14
MATURITY_BUFFER = 190


def _ro(path):
    p = Path(path).resolve(strict=True)
    db = sqlite3.connect(p.as_uri() + "?mode=ro", uri=True, timeout=12)
    db.execute("PRAGMA query_only=ON")
    return db


def freeze(snapshot):
    """Capture exactly what the model said at one real issue time.

    No future observations, identity reassignment, or post-hoc model reruns.
    Fail rather than present a stale, uncalibrated snapshot as a live issue.
    """
    issued = snapshot.get("asof_epoch")
    sha = snapshot.get("model_sha")
    items = snapshot.get("items")
    poll_age = snapshot.get("source_heartbeat_age_seconds")
    if (type(issued) is not int or issued <= 0 or
        not isinstance(sha, str) or re.fullmatch("[0-9a-f]{40}", sha) is None or
        not isinstance(items, dict) or len(items) != 24 or
        type(poll_age) is not int or not 0 <= poll_age <= 180 or
        snapshot.get("production_model_promoted") is not False):
        raise ValueError("not a fresh unpromoted 24-item issue snapshot")
    rows = {}
    for key, forecast in sorted(items.items()):
        if not isinstance(key, str) or key.count(":") != 1 or not isinstance(forecast, dict):
            raise ValueError("invalid physical model item")
        if forecast.get("item_key") != key or forecast.get("asof_epoch") != issued:
            raise ValueError("model item not from this issue epoch")
        events = forecast.get("true_restock_events", forecast.get("restock_events", []))
        if not isinstance(events, list) or len(events) > 64:
            raise ValueError("invalid physical event horizon")
        # The production-facing contract is deliberately deterministic and
        # retains both unreachable first restocks and the selected ordinal.
        decision = build_item_travel_decision(
            forecast, now=issued, poll_age_seconds=poll_age,
        )
        if not decision["all_restock_events_preserved"]:
            raise ValueError("physical event identity was dropped")
        rows[key] = {
            "item_key": key, "issued_epoch": issued, "policy_id": POLICY,
            "source_model_sha": sha, "model_name": forecast.get("model_name"),
            "source_poll_age_seconds": poll_age,
            "physical_events": decision["forecast_events"],
            "selected_event_index": decision["selected_restock_event_index"],
            "decision_status": decision["status"],
            "departure_epoch": decision["estimated_departure_epoch"],
            "departure_deadline_epoch": decision["estimated_departure_deadline_epoch"],
            "arrival_epoch": decision["estimated_arrival_epoch"],
            "arrival_plus_10_epoch": decision["estimated_arrival_plus_grace_epoch"],
            "reconfirm_before_departure": decision["reconfirm_before_departure"],
            "valid_until_epoch": decision["valid_until_epoch"],
            "calibration_state": "UNCALIBRATED",
            "research_only": True, "actual_player_flight": False,
        }
    return {"policy_id": POLICY, "issued_epoch": issued, "source_model_sha": sha,
            "roster_count": 24, "research_only": True, "rows": rows}


def record(batch, sidecar):
    """Append-only private sidecar, never allow overwriting an issue epoch."""
    path = Path(sidecar)
    if path.name != SIDECAR_NAME or path.is_symlink() or not path.parent.is_dir():
        raise ValueError("unapproved prospective sidecar location")
    issued = batch.get("issued_epoch")
    rows = batch.get("rows")
    if (type(issued) is not int or issued <= 0 or not isinstance(rows, dict)
        or len(rows) != 24 or any(r.get("issued_epoch") != issued
                                  or r.get("item_key") != k
                                  or r.get("policy_id") != POLICY
                                  for k, r in rows.items())):
        raise ValueError("incomplete issue batch")
    with closing(sqlite3.connect(path, timeout=12)) as db:
        db.execute("PRAGMA busy_timeout=12000")
        db.execute("""CREATE TABLE IF NOT EXISTS issue_ticks(
            issued_epoch INTEGER PRIMARY KEY,
            model_sha TEXT NOT NULL,
            roster_count INTEGER NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS issued_events(
            item_key TEXT NOT NULL,
            issued_epoch INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY(item_key, issued_epoch)
        )""")
        with db:
            db.execute("INSERT INTO issue_ticks VALUES(?,?,?)",
                       (issued, batch["source_model_sha"], 24))
            db.executemany("INSERT INTO issued_events VALUES(?,?,?)",
                [(k, issued, json.dumps(v, sort_keys=True, separators=(",", ":")))
                 for k, v in sorted(rows.items())])
    os.chmod(path, 0o600)


def _item_evidence(db, item, start, cutoff):
    country, name = item.split(":", 1)
    prior = db.execute(
        """SELECT timestamp,quantity,source FROM stock_history
           WHERE country=? AND lower(item_name)=lower(?) AND timestamp<=?
           ORDER BY timestamp DESC,id DESC LIMIT 1""",
        (country, name, start)).fetchone()
    changes = db.execute(
        """SELECT timestamp,quantity,source FROM stock_history
           WHERE country=? AND lower(item_name)=lower(?) AND timestamp>?
             AND timestamp<=? ORDER BY timestamp,id LIMIT ?""",
        (country, name, start, cutoff, MAX_ITEM_CHANGES + 1)).fetchall()
    if len(changes) > MAX_ITEM_CHANGES:
        raise ValueError("item history exceeds safe report bound")
    rows = ([prior] if prior else []) + changes
    polls = db.execute(
        """SELECT timestamp,source FROM poll_heartbeats
           WHERE mode='poll-cycle' AND success=1 AND timestamp>=?
             AND timestamp<=? ORDER BY timestamp,id LIMIT ?""",
        (start - 180, cutoff, MAX_POLLS + 1)).fetchall()
    if len(polls) > MAX_POLLS:
        raise ValueError("poll history exceeds safe report bound")
    gaps = db.execute(
        """SELECT start_timestamp,end_timestamp FROM collection_gaps
           WHERE start_timestamp<=? AND
                 COALESCE(end_timestamp,9223372036854775807)>=?""",
        (cutoff, start)).fetchall()
    return rows, polls, gaps


def _physical_truth(rows, polls, gaps, *, issued, ordinal, cutoff, estimate):
    # Use the independent physical-zero matcher, NOT a nearest predicted
    # timestamp. Every skipped refill remains part of the ordinal.
    result = match(rows, [p[0] for p in polls], gaps, issued=issued,
                   ordinal=ordinal, cutoff=cutoff, estimate=estimate)
    if result["status"] == "UNKNOWN":
        return result
    end = result.get("restock_by_epoch", cutoff)
    sources = {src for t, src in polls if issued - 180 <= t <= end}
    if len(sources) != 1 or None in sources:
        return {"status": "UNKNOWN", "reason": "POLL_PROVIDER_SWITCH_OR_MISSING"}
    issue_state = next((r[2] for r in reversed(rows) if r[0] <= issued), None)
    if issue_state not in sources:
        return {"status": "UNKNOWN", "reason": "POLL_ITEM_PROVIDER_MISMATCH"}
    return result


def score(*, sidecar, collector, now=None, days=2, max_rows=MAX_ROWS,
          roster=None, arrival_scorer=observation):
    """Score only first-issued item/hour, with physical ordinals frozen.

    Restock time lies inside poll brackets: report certain and possible timing
    hits separately. Future departures are counterfactual UNTIL reconfirmed
    by a newly issued actionable decision, even if stock happened to last.
    """
    if (type(days) is not int or not 1 <= days <= MAX_DAYS or
        type(max_rows) is not int or not 1 <= max_rows <= MAX_ROWS):
        raise ValueError("invalid audit bounds")
    cutoff = int(time.time()) if now is None else now
    if type(cutoff) is not int or cutoff <= 0:
        raise ValueError("invalid audit cutoff")
    if Path(sidecar).resolve(strict=True) == Path(collector).resolve(strict=True):
        raise ValueError("collector must be separate from issue sidecar")
    with closing(_ro(sidecar)) as db:
        raw = db.execute(
            """SELECT item_key,issued_epoch,payload_json FROM issued_events
               WHERE issued_epoch BETWEEN ? AND ?
               ORDER BY issued_epoch,item_key LIMIT ?""",
            (cutoff - days * 86400, cutoff, max_rows + 1)).fetchall()
    if len(raw) > max_rows:
        raise ValueError("too many issues; narrow the date range")
    first = {}
    all_issues = Counter()
    for key, issued, body in raw:
        payload = json.loads(body)
        if (payload.get("item_key") != key or payload.get("issued_epoch") != issued
            or payload.get("policy_id") != POLICY
            or payload.get("research_only") is not True
            or payload.get("actual_player_flight") is not False):
            raise ValueError("untrusted forward issue payload")
        if roster is not None and key not in roster:
            raise ValueError("item outside expected roster")
        all_issues[key] += 1
        first.setdefault((key, issued // 3600), payload)
    by_item = defaultdict(Counter)
    first_event_ids = defaultdict(set)
    chosen_event_ids = defaultdict(set)
    for key in all_issues:
        by_item[key] = Counter()
    by_group = defaultdict(list)
    for (key, _), p in first.items():
        by_group[key].append(p)
    with closing(_ro(collector)) as source:
        for key, issued_rows in sorted(by_group.items()):
            rows, polls, gaps = _item_evidence(
                source, key, min(r["issued_epoch"] for r in issued_rows), cutoff)
            country, name = key.split(":", 1)
            c = by_item[key]
            for p in issued_rows:
                issued = p["issued_epoch"]
                c["first_issued_item_hours"] += 1
                events = p.get("physical_events", [])
                if not isinstance(events, list) or len(events) > 64:
                    raise ValueError("invalid saved physical timeline")
                if events:
                    e = events[0]
                    if e.get("index") != 1:
                        raise ValueError("first physical ordinal changed")
                    observed = _physical_truth(
                        rows, polls, gaps, issued=issued, ordinal=1,
                        cutoff=cutoff, estimate=e["predicted_restock_epoch"])
                    status = observed["status"]
                    c["first_physical_" + status.lower()] += 1
                    if status == "RESOLVED":
                        unique_target = observed["restock_by_epoch"]
                        is_first_issue_for_target = unique_target not in first_event_ids[key]
                        first_event_ids[key].add(unique_target)
                        c["first_physical_scored_hours"] += 1
                        if is_first_issue_for_target:
                            c["distinct_first_physical_restocks"] += 1
                        for seconds in (15, 60, 300, 600):
                            certain = observed["maximum_absolute_error_seconds"] <= seconds
                            possible = observed["minimum_absolute_error_seconds"] <= seconds
                            if certain:
                                c["restock_certain_within_" + str(seconds) + "s"] += 1
                                if is_first_issue_for_target:
                                    c["distinct_restock_certain_within_" + str(seconds) + "s"] += 1
                            if possible:
                                c["restock_possible_within_" + str(seconds) + "s"] += 1
                                if is_first_issue_for_target:
                                    c["distinct_restock_possible_within_" + str(seconds) + "s"] += 1
                        c["restock_min_error_seconds_sum"] += observed["minimum_absolute_error_seconds"]
                        c["restock_max_error_seconds_sum"] += observed["maximum_absolute_error_seconds"]
                else:
                    c["first_physical_no_forecast"] += 1
                index = p.get("selected_event_index")
                depart = p.get("departure_epoch")
                arrival = p.get("arrival_epoch")
                if index is None:
                    if depart is not None or arrival is not None:
                        raise ValueError("abstention has a departure")
                    c["departure_abstain"] += 1
                    continue
                if p.get("decision_status") not in (STATUS_ACTIVE, STATUS_WAIT):
                    raise ValueError("departure contradicts issue status")
                if type(depart) is not int or type(arrival) is not int or depart < issued:
                    raise ValueError("bad saved departure geometry")
                c["departure_proposals"] += 1
                if depart >= p.get("valid_until_epoch", 0):
                    c["future_departure_requires_reconfirmation"] += 1
                else:
                    c["departure_immediately_actionable_at_issue"] += 1
                if index > 0:
                    if type(index) is not int or index > len(events) or index < 1:
                        raise ValueError("selected event not in saved timeline")
                    selected = events[index - 1]
                    if selected.get("index") != index:
                        raise ValueError("selected physical ordinal mismatch")
                    outcome = _physical_truth(
                        rows, polls, gaps, issued=issued, ordinal=index,
                        cutoff=cutoff, estimate=selected["predicted_restock_epoch"])
                    c["chosen_physical_" + outcome["status"].lower()] += 1
                    if outcome["status"] == "RESOLVED":
                        chosen_event_ids[key].add(outcome["restock_by_epoch"])
                elif index == 0:
                    c["chosen_current_stock"] += 1
                else:
                    raise ValueError("invalid current stock index")
                state, hit, _ = arrival_scorer(source, country, name, arrival, cutoff)
                if hit is None:
                    c["landing_" + state.lower()] += 1
                else:
                    c["landing_proxy_hit" if hit else "landing_proxy_miss"] += 1
                    b_state, b_hit, _ = arrival_scorer(
                        source, country, name, issued + (arrival - depart), cutoff)
                    if b_hit is not None:
                        c["matched_leave_now_pairs"] += 1
                        c["matched_recommendation_hits"] += int(hit)
                        c["matched_leave_now_hits"] += int(b_hit)
    for key, c in by_item.items():
        c["distinct_chosen_physical_restocks"] = len(chosen_event_ids[key])
    combined = Counter()
    for c in by_item.values():
        combined.update(c)
    return {
        "status": "PHYSICAL_RESTOCK_PROSPECTIVE_RESEARCH_AUDIT",
        "issued_item_rows": len(raw), "first_issued_item_hours": len(first),
        "asof_epoch": cutoff, "policy_id": POLICY, "research_only": True,
        "source_read_only": True, "actual_player_flights_observed": False,
        "per_country_provider_freshness_certified": False,
        "exact_game_restock_seconds_certified": False,
        "restock_time_basis": "POLL_BRACKET_MIN_MAX_ERROR_NOT_EXACT_GAME_TIME",
        "outcomes_are_independent_restocks": False,
        "distinct_restock_metrics_first_asissued_per_observed_event": True,
        "first_event_is_next_physical_zero_to_positive": True,
        "unreconfirmed_future_departure_is_actionable": False,
        "summary": dict(combined),
        "per_item": {k: dict(c) for k, c in sorted(by_item.items())},
        "warning": "Correlated first-issued item/hour cohorts, global poll-state stock proxy. "
                   "No actual player travel or purchase success verified.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    issue = sub.add_parser("issue")
    issue.add_argument("--source", required=True)
    issue.add_argument("--sidecar", required=True)
    issue.add_argument("--model-sha", required=True)
    issue.add_argument("--assignments")
    issue.add_argument("--preview", action="store_true",
                       help="Do not write to the private sidecar (default)")
    issue.add_argument("--record", action="store_true",
                       help="Opt in to private append-only issue ledger")
    report = sub.add_parser("report")
    report.add_argument("--sidecar", required=True)
    report.add_argument("--collector", required=True)
    report.add_argument("--days", type=int, default=2)
    args = parser.parse_args()
    if args.command == "issue":
        if args.record and args.preview:
            parser.error("--record and --preview are incompatible")
        assignments = json.loads(Path(args.assignments).read_text()) if args.assignments else None
        now = int(time.time())
        snapshot = prepare(args.source, model_sha=args.model_sha,
                           assignments=assignments, now=now)
        batch = freeze(snapshot)
        if args.record:
            record(batch, args.sidecar)
        print(json.dumps({
            "status": "RECORDED_IMMUTABLE_ISSUE" if args.record else "NO_WRITE_PREVIEW",
            "asof_epoch": now, "item_count": 24,
            "physical_events": sum(len(r["physical_events"]) for r in batch["rows"].values()),
            "model_sha": args.model_sha, "collector_written": False,
            "production_promotion": False,
        }, sort_keys=True))
    else:
        print(json.dumps(score(sidecar=args.sidecar, collector=args.collector,
                               days=args.days), sort_keys=True))


if __name__ == "__main__":
    main()
