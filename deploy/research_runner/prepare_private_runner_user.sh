#!/usr/bin/env bash
# Prepare ONLY the isolated VM research user's Python environment.
# Never edits Torn-Fren collector, websites, pinned production models,
# database permissions, firewall configuration, or existing timers.
set -euo pipefail
[[ "$(id -un)" == "ubuntu" ]] || { echo "STOP: run as ubuntu"; exit 1; }
sudo -n true || { echo "STOP: sudo unavailable"; exit 1; }

SRC=/opt/torn-fren/data/stock_history.db
SNAP=/var/lib/torn-fren-research/stock_history_research.db
ROSTER=/home/ubuntu/torn-fren-private-models/v160_stage/pinned/research/v38_roster.json
HOME_RUNNER=/var/lib/torn-fren-research-runner
VENV=$HOME_RUNNER/.venv

echo "===== CONFIRM PRODUCTION/RESEARCH DATA ISOLATION ====="
test "$(uname -m)" = aarch64 || { echo "STOP: expected Oracle ARM64 runner"; exit 1; }
id tornresearch >/dev/null || { echo "STOP: tornresearch missing"; exit 1; }
test "$(id -gn tornresearch)" = tornfren-research || {
  echo "STOP: unexpected research group"; exit 1;
}
systemctl is-active --quiet torn-fren-research-snapshot.timer || {
  echo "STOP: research snapshot refresh timer inactive"; exit 1;
}
systemctl is-active --quiet torn-fren-v160-forward24.timer || {
  echo "STOP: existing V160 timer unexpectedly inactive"; exit 1;
}
sudo -n -u tornresearch test -r "$SNAP" || {
  echo "STOP: sanitized research data unavailable"; exit 1;
}
if sudo -n -u tornresearch test -r "$SRC"; then
  echo "STOP: research user can access LIVE source"; exit 1;
fi
if sudo -n -u tornresearch test -r "$ROSTER"; then
  echo "STOP: research user can access PRIVATE model stage"; exit 1;
fi
test -d "$HOME_RUNNER" && test ! -L "$HOME_RUNNER" || {
  echo "STOP: runner home missing or symlinked"; exit 1;
}
[[ "$(stat -c %U -- "$HOME_RUNNER")" == tornresearch ]] || {
  echo "STOP: research runner home owner mismatch"; exit 1;
}
if test -e "$HOME_RUNNER/.runner"; then
  echo "STOP: existing GitHub runner configuration found; do not overwrite"; exit 1;
fi

echo "===== CHECK SANITIZED DB SCHEMA AND FRESHNESS ====="
sudo -n -u tornresearch python3 -B - "$SNAP" <<'CHECK'
import sqlite3,sys,time
from pathlib import Path
p=Path(sys.argv[1]).resolve(strict=True)
con=sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=8)
con.execute("PRAGMA query_only=ON")
meta=dict(con.execute("SELECT key,value FROM research_metadata"))
if meta.get("schema")!="torn-fren-research-stock-v1" or meta.get("roster_size")!="24":
    raise SystemExit("STOP: unsupported snapshot type or roster")
if meta.get("sanitized_stock_only")!="true":
    raise SystemExit("STOP: stock snapshot isn't sanitized")
if time.time()-int(meta["source_cutoff_epoch"])>7200:
    raise SystemExit("STOP: research snapshot too old")
tables={row[0] for row in con.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")}
if tables!={"stock_history","collection_gaps","poll_heartbeats","research_metadata"}:
    raise SystemExit("STOP: unexpected columns/tables in research snapshot")
print("PASS: 24-item sanitized research snapshot; rows="+meta["row_count"])
con.close()
CHECK

echo "===== CREATE INDEPENDENT RESEARCH PYTHON ENVIRONMENT ====="
if [[ -e "$VENV" && ! -x "$VENV/bin/python" ]]; then
  echo "STOP: existing incomplete runner virtual environment"; exit 1;
fi
if [[ ! -d "$VENV" ]]; then
  sudo -n -H -u tornresearch python3 -m venv "$VENV"
fi
sudo -n -H -u tornresearch env PYTHONNOUSERSITE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
 "$VENV/bin/python" -m pip install --no-input --only-binary=:all: 'numpy==1.26.4'
sudo -n -H -u tornresearch env PYTHONNOUSERSITE=1 "$VENV/bin/python" - <<'CHECK'
import numpy, sqlite3,platform
assert numpy.__version__=="1.26.4"
print("PASS: isolated research venv; numpy="+numpy.__version__+
      "; CPU="+platform.machine())
CHECK
if sudo -n -u tornresearch test -r "$SRC"; then
  echo "STOP: production isolation changed during Python setup"; exit 1;
fi
echo "SUCCESS: private research runner Python environment prepared on ARM64."
echo "NEXT: register a self-hosted ARM64 runner in PRIVATE GitHub repository."
echo "NO GitHub token used; NO production services, data, or websites altered."
