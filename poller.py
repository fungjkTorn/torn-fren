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
    invalidate_pending_forecasts_crossing_gap,
    is_tracked_item,
    resolve_forecast_audits,
)
from services.prediction_v2_live import build_live_prediction_v2

POLL_INTERVAL_SECONDS = 30


def run():
    print(f"Starting poller — one export call every {POLL_INTERVAL_SECONDS}s. Press Ctrl+C to stop.")

    # Never freeze fresh prediction/audit records from stale pre-outage state.
    # If the machine/server was asleep or offline, the first successful poll
    # will establish a recovery collection gap before prediction work resumes.
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
    else:
        try:
            seeded = seed_prediction_audits()
            if seeded:
                print(f"Seeded {seeded} current prediction audit records.")
        except Exception as exc:
            print(f"Prediction audit seed error: {exc}")

        # Start multi-cycle forecast auditing immediately for items that already
        # have a Prediction v2 profile from prior graph/Discord use.
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

    while True:
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

                # IMPORTANT: success is recorded only after every DB save has
                # completed.  The previous version recorded success before the
                # save, which hid the changed_items outage from continuity checks.
                heartbeat = record_poll_heartbeat(True, source=source)

            except Exception as exc:
                try:
                    record_poll_heartbeat(False, source=source, error=str(exc)[:500])
                except Exception:
                    pass
                print(f"Poll cycle save error: {exc}")
                changed_by_country = {}

            # A recovery snapshot tells us current quantities but not WHEN
            # anything changed while collection was offline.  Quarantine this
            # entire change burst from both audit systems.
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
                    "Current stock was saved, but recovery transitions are "
                    "quarantined from model/audit ground truth."
                )

                try:
                    invalidated = invalidate_pending_forecasts_crossing_gap(
                        gap_start,
                        gap_end,
                        reason="collector heartbeat recovery gap",
                    )
                    if invalidated:
                        print(
                            f"Invalidated {invalidated} pending multi-cycle "
                            "forecast point(s) that crossed the outage."
                        )
                except Exception as exc:
                    print(f"Forecast gap invalidation error: {exc}")

                # Do not run per-item prediction work on the recovery burst.
                changed_by_country = {}

            # Prediction auditing is downstream of collection. Audit failures
            # must never turn a successful stock collection into a failed poll.
            if isinstance(changed_by_country, dict):
                for country, item_names in changed_by_country.items():
                    for item_name in item_names:
                        try:
                            result = update_prediction_audits_for_item(country, item_name)
                            if result["resolved"] or result["recorded"]:
                                print(
                                    f"prediction audit {country}/{item_name}: "
                                    f"resolved={result['resolved']}, recorded={result['recorded']}"
                                )
                        except Exception as exc:
                            print(f"Prediction audit error for {country}/{item_name}: {exc}")

                        # Multi-cycle P1/P2/P3/... auditor.
                        # Only tracked/profiled items get forecast refreshes, so
                        # the poller does not run expensive Prediction v2 models
                        # for every foreign item on every 30-second cycle.
                        try:
                            resolved_forecasts = resolve_forecast_audits(country, item_name)

                            if is_tracked_item(country, item_name):
                                refreshed = build_live_prediction_v2(
                                    country,
                                    item_name,
                                    audit_source="poller",
                                    record_audit=True,
                                )
                                active_num = (
                                    (refreshed.get("display_prediction") or {})
                                    .get("prediction_number")
                                )
                                if resolved_forecasts or active_num:
                                    print(
                                        f"forecast audit {country}/{item_name}: "
                                        f"resolved={resolved_forecasts}, "
                                        f"active=P{active_num or '-'}"
                                    )
                        except Exception as exc:
                            print(f"Forecast audit error for {country}/{item_name}: {exc}")

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

        print(f"Sleeping {POLL_INTERVAL_SECONDS} seconds...\n")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run()
