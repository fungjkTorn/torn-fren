import time
from services.history_service import save_snapshot

COUNTRIES_TO_POLL = ["mex", "cay", "can", "haw", "uni", "arg", "swi", "jap", "chi", "uae", "sou"]  
POLL_INTERVAL_SECONDS = 30


def run():
    print(f"Polling {COUNTRIES_TO_POLL} every {POLL_INTERVAL_SECONDS}s. Press Ctrl+C to stop.")
    while True:
        for country in COUNTRIES_TO_POLL:
            save_snapshot(country)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run()