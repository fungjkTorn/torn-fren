import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "stock_history.db"
LOG_PATH = Path(__file__).parent / "data" / "connection_events.log"


def fmt(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %I:%M:%S %p")


def main():
    print("=== Torn Fren runtime diagnostics ===\n")

    if DB_PATH.exists():
        con = sqlite3.connect(DB_PATH)
        cols = {row[1] for row in con.execute("PRAGMA table_info(poll_heartbeats)")}
        if {"success", "mode"}.issubset(cols):
            rows = con.execute(
                """
                SELECT timestamp, source, success, COALESCE(error, '')
                FROM poll_heartbeats
                WHERE mode = 'poll-cycle'
                ORDER BY timestamp DESC
                LIMIT 20
                """
            ).fetchall()
            print("Last poll-cycle heartbeats:")
            if not rows:
                print("  No new poll-cycle heartbeats yet. Restart poller.py with the patch installed.")
            for ts, source, success, error in reversed(rows):
                state = "OK" if success else "FAIL"
                suffix = f" | {error}" if error else ""
                print(f"  {fmt(ts)} | {state:<4} | {source}{suffix}")
        else:
            print("Heartbeat schema is still legacy. Restart the patched poller once to migrate it.")
        con.close()
    else:
        print("Database not found.")

    print("\nRecent Discord connection diagnostics:")
    if LOG_PATH.exists():
        lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-30:]
        for line in lines:
            print("  " + line)
    else:
        print("  No connection_events.log yet. It will be created by the patched bot/main.py.")


if __name__ == "__main__":
    main()
