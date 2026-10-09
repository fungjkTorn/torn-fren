import threading
import time

from services.stock_provider import get_travel_export
from services.history_service import (
    get_collector_recovery_status,
    record_poll_heartbeat,
    save_all_snapshots,
    seed_prediction_audits,
    update_prediction_audits_for_item,
)
from services.forecast_auditor import (
    get_profiled_items,
    get_tracked_items,
    is_tracked_item,
    resolve_forecast_audits,
)
from services.prediction_v2_live import build_live_prediction_v2
from services.shadow_model_auditor import update_shadow_models
from research.v38_gap_recovery import (
    pending as gap_recovery_pending,
)

POLL_INTERVAL_SECONDS = 30

# Audit/model work can be much slower than collection. Keep it off the polling
# path and coalesce repeated changes for the same item while the worker is busy.
_AUDIT_PENDING = set()
_AUDIT_LOCK = threading.Lock()
_AUDIT_EVENT = threading.Event()
_AUDIT_STOP = threading.Event()


# Recovery invalidation is performed by a separate resource-capped
# systemd one-shot worker. Never create expensive recovery threads here.
# The heartbeat writer persists the gap AND its queue record atomically.
def _schedule_gap_recovery(gap_start, gap_end):
    print(
        f"recovery audit durably queued: {int(gap_start)}..{int(gap_end)}; "
        "external torn-fren-gap-recovery.timer will process it",
        flush=True,
    )
    return {"status": "ENQUEUED", "gap_start": int(gap_start),
            "gap_end": int(gap_end)}


def _schedule_item_audits(changed_by_country):
    if not isinstance(changed_by_country, dict):
        return
    with _AUDIT_LOCK:
        for country, item_names in changed_by_country.items():
            for item_name in item_names:
                _AUDIT_PENDING.add((country, item_name))
    _AUDIT_EVENT.set()


def _run_item_audits(country, item_name):
    try:
        result = update_prediction_audits_for_item(country, item_name)
        if result["resolved"] or result["recorded"]:
            print(
                f"prediction audit {country}/{item_name}: "
                f"resolved={result['resolved']}, recorded={result['recorded']}"
            )
    except Exception as exc:
        print(f"Prediction audit error for {country}/{item_name}: {exc}")

    try:
        resolved_forecasts = resolve_forecast_audits(country, item_name)
        if is_tracked_item(country, item_name):
            refreshed = build_live_prediction_v2(
                country,
                item_name,
                audit_source="poller",
                record_audit=True,
            )
            active_num = (refreshed.get("display_prediction") or {}).get(
                "prediction_number"
            )
            if resolved_forecasts or active_num:
                print(
                    f"forecast audit {country}/{item_name}: "
                    f"resolved={resolved_forecasts}, active=P{active_num or '-'}"
                )
    except Exception as exc:
        print(f"Forecast audit error for {country}/{item_name}: {exc}")

    # Experimental travel-goal challengers run only in shadow mode. They never
    # drive live guidance; they simply accumulate forward-test evidence.
    if country.lower() == "jap" and item_name.lower() == "xanax":
        try:
            shadow = update_shadow_models(country, item_name)
            if shadow.get("resolved") or shadow.get("recorded"):
                print(
                    f"shadow audit {country}/{item_name}: "
                    f"resolved={shadow['resolved']}, recorded={shadow['recorded']}"
                )
        except Exception as exc:
            print(f"Shadow model audit error for {country}/{item_name}: {exc}")


def _audit_worker():
    while not _AUDIT_STOP.is_set():
        _AUDIT_EVENT.wait(timeout=1.0)
        if _AUDIT_STOP.is_set():
            return

        while True:
            # Do not resolve new audit points against an unprocessed outage.
            # Queued gaps remain visible and retryable after a poller restart.
            try:
                if gap_recovery_pending()["pending"]:
                    _AUDIT_STOP.wait(timeout=2.0)
                    continue
            except Exception as exc:
                print(f"recovery backlog check error: {type(exc).__name__}",flush=True)
                _AUDIT_STOP.wait(timeout=2.0)
                continue
            with _AUDIT_LOCK:
                if not _AUDIT_PENDING:
                    _AUDIT_EVENT.clear()
                    break
                pending = sorted(_AUDIT_PENDING)
                _AUDIT_PENDING.clear()

            for country, item_name in pending:
                _run_item_audits(country, item_name)


def _seed_audits_async():
    """Seed audit state without delaying the first production poll."""
    try:
        recovery_status = get_collector_recovery_status()
    except Exception as exc:
        print(f"Collector startup status error: {exc}")
        recovery_status = {"stale": True, "age_seconds": None}

    if recovery_status.get("stale"):
        age = recovery_status.get("age_seconds")
        age_text = f"{age}s" if age is not None else "unknown"
        print(
            "Collector heartbeat is stale "
            f"({age_text} since last verified poll). "
            "Skipping startup prediction/audit seeding until recovery is recorded."
        )
        return

    try:
        seeded = seed_prediction_audits()
        if seeded:
            print(f"Seeded {seeded} current prediction audit records.")
    except Exception as exc:
        print(f"Prediction audit seed error: {exc}")

    try:
        profiled = get_profiled_items()
        tracked = set((c.lower(), i.lower()) for c, i in get_tracked_items())
        seeded_forecasts = 0

        for country, item_name in profiled:
            if (country.lower(), item_name.lower()) in tracked:
                continue
            try:
                build_live_prediction_v2(
                    country,
                    item_name,
                    audit_source="poller-startup",
                    record_audit=True,
                )
                seeded_forecasts += 1
            except Exception as exc:
                print(f"Forecast audit seed error for {country}/{item_name}: {exc}")

        if seeded_forecasts:
            print(f"Seeded {seeded_forecasts} Prediction v2 forecast audit item(s).")
    except Exception as exc:
        print(f"Forecast audit startup error: {exc}")


def run():
    print(f"Starting poller — one export call every {POLL_INTERVAL_SECONDS}s. Press Ctrl+C to stop.")

    worker = threading.Thread(target=_audit_worker, name="torn-fren-audit-worker", daemon=True)
    worker.start()
    threading.Thread(
        target=_seed_audits_async,
        name="torn-fren-audit-seed",
        daemon=True,
    ).start()

    while True:
        cycle_started = time.monotonic()
        export = None

        try:
            export = get_travel_export()
        except Exception as exc:
            try:
                record_poll_heartbeat(False, source="fetch-error", error=str(exc)[:500])
            except Exception:
                pass
            print(f"Travel export error: {exc}")

        if export:
            source = export.get("source", "unknown")
            heartbeat = None

            try:
                print(f"Saving all country snapshots from {source}...")
                changed_by_country = save_all_snapshots(export)

                # Success means provider fetch AND every DB save completed.
                heartbeat = record_poll_heartbeat(True, source=source)

            except Exception as exc:
                try:
                    record_poll_heartbeat(False, source=source, error=str(exc)[:500])
                except Exception:
                    pass
                print(f"Poll cycle save error: {exc}")
                changed_by_country = {}

            recovered_from_gap = bool(
                isinstance(heartbeat, dict)
                and heartbeat.get("recovered_from_gap")
            )

            if recovered_from_gap:
                gap_start = heartbeat.get("gap_start_timestamp")
                gap_end = heartbeat.get("gap_end_timestamp")
                elapsed = heartbeat.get("elapsed_since_success_seconds")
                print(
                    "COLLECTION RECOVERY: "
                    f"{elapsed}s without verified polling. "
                    "Recovery transitions are treated as uncertain event boundaries; "
                    "same-state item gaps may be bridged."
                )

                try:
                    queued = _schedule_gap_recovery(gap_start, gap_end)
                    print(
                        f"Recovery audit queued for background processing: "
                        f"{queued['gap_start']}..{queued['gap_end']}",
                        flush=True,
                    )
                except Exception as exc:
                    print(
                        f"Recovery audit enqueue failed ({type(exc).__name__}); "
                        "collector continues but forecast audit needs attention.",
                        flush=True,
                    )

            # Never block collection on prediction/model work. Even a recovery
            # burst is useful to the async worker; event-aware validation decides
            # which item transitions are exact vs uncertain.
            _schedule_item_audits(changed_by_country)

        elif export is None:
            try:
                record_poll_heartbeat(
                    False,
                    source="none",
                    error="YATA and Prometheus both unavailable",
                )
            except Exception:
                pass
            print("No travel export available this cycle.")

        elapsed = time.monotonic() - cycle_started
        sleep_seconds = max(0.0, POLL_INTERVAL_SECONDS - elapsed)
        print(
            f"Poll cycle completed in {elapsed:.1f}s; "
            f"sleeping {sleep_seconds:.1f}s...\n"
        )
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    run()