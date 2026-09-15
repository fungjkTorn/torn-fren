import time
from services.stock_provider import get_travel_export
from services.history_service import save_all_snapshots

POLL_INTERVAL_SECONDS = 30


def run():
    print(f"Starting poller — one export call every {POLL_INTERVAL_SECONDS}s. Press Ctrl+C to stop.")

    while True:
        export = get_travel_export()

        if export:
            print("Saving all country snapshots...")
            save_all_snapshots(export)
        else:
            print("No travel export available this cycle.")

        print(f"Sleeping {POLL_INTERVAL_SECONDS} seconds...\n")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run()