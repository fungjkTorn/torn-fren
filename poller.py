"""30-second stock collector only; routine audits use durable v39 worker.

Do not import V2 predictor or start audit/seeding threads in this service.
"""
import time
from services.stock_provider import get_travel_export
from services.history_service import record_poll_heartbeat, save_all_snapshots

POLL_INTERVAL_SECONDS = 30


def _schedule_gap_recovery(gap_start,gap_end):
    # Heartbeat writer persisted queue record in same transaction.
    print(f"recovery audit durably queued: {int(gap_start)}..{int(gap_end)}; "
          "external torn-fren-gap-recovery.timer will process it",flush=True)
    return {"status":"ENQUEUED","gap_start":int(gap_start),
            "gap_end":int(gap_end)}


def run():
    print(f"Starting poller — one export call every {POLL_INTERVAL_SECONDS}s. Press Ctrl+C to stop.")

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

            # Stock transitions were enqueued atomically in history_service,
            # alongside their actual DB inserts. No model work in this process.

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