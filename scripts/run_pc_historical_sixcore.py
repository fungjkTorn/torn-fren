"""Windows-friendly 6-worker overnight *historical* tournament.

This runs the EXISTING four physical-restock clocks + both departure policies,
alongside leave-now, in independent per-item Python processes. It uses a LOCAL
historical SQLite snapshot opened read-only; it never talks to the Torn API,
SSH, live VM, game account or production services.

Example (PowerShell from repo root):
  py -3 scripts/run_pc_historical_sixcore.py --source "C:\\data\\torn-stock-history.db" --days 6 --workers 6

--smoke limits the first run to Jaguar and Japan Xanax (1 day).
--output accepts a stable directory to resume incomplete runs.
"""
from __future__ import annotations

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parents[1]
MAX_WORKERS = 6
MAX_DAYS = 6
ROSTER_PATH = BASE / "research" / "v38_roster.json"
MODES = ("phase_empirical", "interval_median", "interval_ridge",
         "phase_recursive_ridge")
WINDOWS = ("expected", "bounded")
CSV_FIELDS = ("item", "policy", "restock_model", "split", "starts",
              "flight_known", "flight_success_fraction", "departure_coverage",
              "mean_wait_minutes", "matched_leave_now", "model_only_hits",
              "leave_now_only_hits", "restock_hourly_scored",
              "restock_distinct_targets", "restock_mean_error_minutes",
              "restock_within_60s", "restock_within_10m", "notes")


def exact_roster():
    with ROSTER_PATH.open(encoding="utf-8") as handle:
        data = json.load(handle)
    base = data["items"]
    if len(base) != 22:
        raise ValueError("Unrecognized pinned 22-key roster")
    names = sorted(set(base) | {"can:Xanax", "uni:Xanax"})
    if len(names) != 24 or "jap:Xanax" not in names:
        raise ValueError("Unrecognized all-24 experiment roster")
    return names


def git_sha():
    p = subprocess.run(["git", "rev-parse", "HEAD"], cwd=BASE,
                       capture_output=True, text=True, check=True)
    sha = p.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40}", sha) is None:
        raise ValueError("Not a pinned Git checkout")
    return sha


def hash_source(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_local_source(source):
    source = Path(source).expanduser().resolve(strict=True)
    if not source.is_file() or source.suffix.lower() not in (".db", ".sqlite", ".sqlite3"):
        raise ValueError("Provide a local SQLite history .db/.sqlite/.sqlite3 file")
    if source.stat().st_size < 4096:
        raise ValueError("SQLite file is empty/too small")
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=12) as db:
        db.execute("PRAGMA query_only=ON")
        tables = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        need = {"stock_history", "poll_heartbeats", "collection_gaps"}
        if not need <= tables:
            raise ValueError("Historical SQLite is missing " +
                             ",".join(sorted(need - tables)))
        heartbeat = db.execute("""SELECT MAX(timestamp) FROM poll_heartbeats
            WHERE mode='poll-cycle' AND success=1""").fetchone()[0]
        if heartbeat is None:
            raise ValueError("Historical file has no successful poll evidence")
        metadata = {}
        if "research_metadata" in tables:
            metadata = dict(db.execute("SELECT key,value FROM research_metadata"))
    return source, {"max_heartbeat_epoch": int(heartbeat),
                    "research_metadata": {k: metadata.get(k) for k in
                        ("sanitized_stock_only", "roster_size",
                         "row_count", "source_cutoff_epoch")}}


def slug(item):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", item.replace(":", "__")).strip("_")


def commands_for(item, *, source, sha, days, target):
    return ([sys.executable, "-m", "research.restock_event_clock",
             "--source", str(source), "--out", str(target),
             "--model-sha", sha, "--days", str(days),
             "--item-key", item])


def _paths(root, item):
    folder = root / "items" / slug(item)
    return folder, folder / "result.json"


def _valid_result(record, *, item, sha, days):
    if not isinstance(record, dict):
        return False
    return (record.get("item_key") == item
            and record.get("_local_model_sha") == sha
            and record.get("_local_days") == days
            and record.get("production_promotion") is False
            and isinstance(record.get("restock_timing"), dict)
            and isinstance(record.get("chronological_slices"), dict))


def _task(item, *, source, root, sha, days, timeout):
    folder, archive = _paths(root, item)
    folder.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        try:
            stored = json.loads(archive.read_text(encoding="utf-8"))
            if _valid_result(stored, item=item, sha=sha, days=days):
                return dict(item=item, status="CACHED", result=stored,
                            elapsed_seconds=0)
        except (ValueError, OSError):
            pass
    # Never modify or delete partial experiments. Retries receive a unique
    # directory, and completed JSON writes are atomic.
    attempt = folder / ("attempt_" + str(time.time_ns()))
    log = folder / (attempt.name + ".log")
    env = os.environ.copy()
    env.update({"PYTHONPATH": str(BASE),
                "TORNFREN_REPLAY_WORK": str(BASE),
                "TORNFREN_REPLAY_PINNED_RESEARCH": str(BASE / "research"),
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1",
                "PYTHONUNBUFFERED": "1"})
    started = time.monotonic()
    cmd = commands_for(item, source=source, sha=sha,
                       days=days, target=attempt)
    try:
        proc = subprocess.run(cmd, cwd=BASE, env=env,
                              capture_output=True, text=True, errors="replace",
                              timeout=timeout, check=False)
        log.write_text("COMMAND: " + " ".join(cmd) + "\nEXIT: " +
                       str(proc.returncode) + "\nSTDOUT\n" + proc.stdout +
                       "\nSTDERR\n" + proc.stderr, encoding="utf-8")
        if proc.returncode:
            return dict(item=item, status="ERROR", error="exit_" +
                        str(proc.returncode), log=str(log),
                        elapsed_seconds=round(time.monotonic()-started, 2))
        report_file = attempt / (item.replace(":", "-").replace(" ", "_") + ".json")
        payload = json.loads(report_file.read_text(encoding="utf-8"))
        payload["_local_model_sha"] = sha
        payload["_local_days"] = days
        if not _valid_result(payload, item=item, sha=sha, days=days):
            raise ValueError("Unexpected or incomplete item metrics")
        tmp = archive.with_suffix(".json.next")
        tmp.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(archive)
        return dict(item=item, status="COMPLETED", result=payload,
                    elapsed_seconds=round(time.monotonic()-started, 2))
    except subprocess.TimeoutExpired as exc:
        log.write_text("TIMEOUT: " + str(exc) + "\n", encoding="utf-8")
        return dict(item=item, status="TIMEOUT", log=str(log),
                    elapsed_seconds=round(time.monotonic()-started, 2))
    except (OSError, ValueError, KeyError) as exc:
        log.write_text(type(exc).__name__ + ": " + str(exc) + "\n",
                       encoding="utf-8")
        return dict(item=item, status="ERROR", error=type(exc).__name__,
                    log=str(log),
                    elapsed_seconds=round(time.monotonic()-started, 2))


def score_rows(item, report):
    slices = report.get("chronological_slices", {})
    timing = report.get("restock_timing", {})
    out = []
    for split in ("earlier_development", "later_validation"):
        policies = slices.get(split, {})
        for name in list(p + "_" + w for p in MODES for w in WINDOWS) + ["leave_now"]:
            entry = policies.get(name, {})
            family = name.rsplit("_", 1)[0] if name != "leave_now" else "LEAVE_NOW"
            rt = timing.get(family, {}).get("chronological_slices", {}).get(split, {})
            paired = entry.get("matched_vs_now") or {}
            out.append(dict(item=item, policy=name, restock_model=family,
                split=split, starts=entry.get("starts"),
                flight_known=entry.get("scored"),
                flight_success_fraction=entry.get("success_fraction"),
                departure_coverage=entry.get("departure_coverage"),
                mean_wait_minutes=entry.get("mean_wait_minutes"),
                matched_leave_now=paired.get("matched_resolved"),
                model_only_hits=paired.get("challenger_only_success"),
                leave_now_only_hits=paired.get("baseline_only_success"),
                restock_hourly_scored=rt.get("scored"),
                restock_distinct_targets=rt.get("distinct_target_restocks"),
                restock_mean_error_minutes=rt.get("mean_absolute_error_minutes"),
                restock_within_60s=(timing.get(family, {})
                                   .get("within_60_seconds") if split == "later_validation"
                                   else None),
                restock_within_10m=(timing.get(family, {})
                                   .get("within_10_minutes") if split == "later_validation"
                                   else None),
                notes="CORRELATED_UTC_HOURLY_SAMPLED_POLL_PROXIES"))
    return out


def write_summary(root, *, source, source_sha, sha, days, requested, outcomes):
    complete = {k: r["result"] for k, r in outcomes.items()
                if r["status"] in ("CACHED", "COMPLETED")}
    all_rows = [row for key, payload in sorted(complete.items())
                for row in score_rows(key, payload)]
    csv_path = root / "scores.csv"
    tmp = csv_path.with_suffix(".csv.next")
    with tmp.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)
    tmp.replace(csv_path)
    short = {key: {field: value for field, value in outcome.items()
                  if field != "result"} for key, outcome in sorted(outcomes.items())}
    status = "COMPLETE" if len(complete) == len(requested) else "PARTIAL_NO_PROMOTION"
    report = dict(kind="PC_SIX_CORE_CAUSAL_PHYSICAL_RESTOCK_HISTORICAL",
                  timestamp_utc=datetime.now(timezone.utc).isoformat(),
                  status=status, completed=len(complete), requested=len(requested),
                  model_sha=sha, source_sha256=source_sha,
                  local_source=str(source), days=days,
                  item_status=short, performance_csv=str(csv_path),
                  production_modified=False, actual_player_flights=False,
                  source_written=False, automatic_model_promotion=False,
                  note="Repeated UTC hourly cohorts share physical restocks. "
                  "Every forecast uses historical preissue observations only; "
                  "arrival stock is a sampled-poll proxy, not a verified game purchase.")
    tmp = (root / "summary.json.next")
    tmp.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    tmp.replace(root / "summary.json")
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True,
                   help="LOCAL historical SQLite .db path; source is NEVER modified")
    p.add_argument("--output", type=Path,
                   help="Stable output folder; reused to resume unfinished items")
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--days", type=int, default=6)
    p.add_argument("--timeout-per-item", type=int, default=3600)
    p.add_argument("--smoke", action="store_true",
                   help="Only Jaguar and Japan Xanax, one day")
    p.add_argument("--item-key", action="append",
                   help="Optional repeated item-specific bounded experiment")
    args = p.parse_args(argv)
    if not 1 <= args.workers <= MAX_WORKERS:
        p.error("Use 1 to 6 CPU workers")
    if not 1 <= args.days <= MAX_DAYS:
        p.error("Use 1 to 6 historical days")
    if not 30 <= args.timeout_per_item <= 7200:
        p.error("Per-item timeout must be 30..7200 seconds")
    source, metadata = verify_local_source(args.source)
    sha = git_sha()
    roster = exact_roster()
    requested = sorted(args.item_key or
                       (["mex:Jaguar Plushie", "jap:Xanax"] if args.smoke else roster))
    if args.smoke and not args.item_key:
        args.days = 1
    if len(set(requested)) != len(requested) or not set(requested) <= set(roster):
        p.error("Item selection must be unique and from the pinned 24-item roster")
    if args.output is None:
        root = BASE / "historical_pc_results" / datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ")
    else:
        root = args.output.expanduser().resolve()
    if source == root or root == BASE or source in root.parents:
        raise ValueError("Output must not overwrite source or repository root")
    root.mkdir(parents=True, exist_ok=True)
    fingerprint_path = root / "input_manifest.json"
    source_sha = hash_source(source)
    fingerprint = dict(model_sha=sha, source_sha256=source_sha, days=args.days,
                       requested_items=requested,source_meta=metadata)
    if fingerprint_path.exists():
        old = json.loads(fingerprint_path.read_text(encoding="utf-8"))
        if old != fingerprint:
            raise ValueError("Output folder belongs to a different source/model/roster")
    else:
        fingerprint_path.write_text(json.dumps(fingerprint, sort_keys=True,
                                              indent=2)+"\n", encoding="utf-8")
    print("LOCAL RESEARCH SOURCE:", source)
    print("MODEL:", sha, "ITEMS:", len(requested),
          "DAYS:", args.days, "WORKERS:", args.workers, flush=True)
    print("RESULTS:", root, flush=True)
    if args.smoke:
        print("SMOKE MODE: two items, one historical day", flush=True)
    completed = {}
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        tasks = {pool.submit(_task, item, source=source, root=root, sha=sha,
                             days=args.days, timeout=args.timeout_per_item): item
                 for item in requested}
        for future in as_completed(tasks):
            item = tasks[future]
            try:
                completed[item] = future.result()
            except Exception as exc:
                completed[item] = dict(item=item, status="ERROR",
                                       error=type(exc).__name__ + ": " + str(exc)[:160])
            status = completed[item]["status"]
            report = write_summary(root,source=source,source_sha=source_sha,
                                   sha=sha,days=args.days,requested=requested,
                                   outcomes=completed)
            print(f"[{len(completed)}/{len(requested)}] {item}: {status}; "
                  f"completed {report['completed']}", flush=True)
    after_sha = hash_source(source)
    if after_sha != source_sha:
        raise RuntimeError("Local source history changed during replay; results invalid")
    total = time.monotonic()-start
    print("FINISHED",report["status"],"SECONDS",round(total, 1))
    print("OPEN",root / "scores.csv")
    print("OPEN",root / "summary.json")
    return 0 if report["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
