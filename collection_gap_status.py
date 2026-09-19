from datetime import datetime
from services.history_service import (
    get_collection_gaps,
    get_collector_recovery_status,
    reconcile_collection_gaps,
)


def fmt(ts):
    if ts is None:
        return "OPEN"
    return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %I:%M:%S %p")


def main():
    reconcile_collection_gaps()

    status = get_collector_recovery_status()
    print("=== Collector continuity ===")
    print(f"stale: {status['stale']}")
    print(f"last successful poll: {fmt(status['last_success_timestamp'])}")
    print(f"age seconds: {status['age_seconds']}")
    print(f"gap threshold: {status['threshold_seconds']}s")

    print("\n=== Known collection gaps ===")
    gaps = get_collection_gaps()
    if not gaps:
        print("none")
        return

    for gap in gaps[-10:]:
        start = fmt(gap["start_timestamp"])
        end = fmt(gap["end_timestamp"])
        print(f"{start} -> {end} | {gap['reason']}")


if __name__ == "__main__":
    main()
