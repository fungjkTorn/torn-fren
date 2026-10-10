#!/usr/bin/env bash
# V38 private five-model launcher. Operator approved canary; no public routing.
# Must follow a healthy V39 production CPU release and successful off-prod
# read-only frozen model workload. Stops without timer activation on failure.
set -euo pipefail
V39_PROD_SHA="e9ba974c96553ea36f31951b94901b7379b22624"
REF="research/v38-full-roster-live-prep-20261009"
TARGET="${1:-}"
ROOT="/home/ubuntu/torn-fren-v38-probe"
DB="/opt/torn-fren/data/stock_history.db"

if [[ ! "$TARGET" =~ ^[0-9a-f]{40}$ ]]; then
  echo "STOP: pass exact SHA of passing GitHub research CI" >&2
  exit 2
fi

echo "===== VERIFY PRODUCTION STILL RUNS SAFE V39 ====="
test "$(git -C /opt/torn-fren rev-parse HEAD)" = "$V39_PROD_SHA"
for unit in torn-fren-poller.service torn-fren-web.service \
    torn-fren-bot.service torn-fren-gap-recovery.timer \
    torn-fren-routine-audit.timer; do
  test "$(systemctl is-active "$unit")" = active || {
    echo "STOP: required V39 component unavailable: $unit" >&2
    exit 2
  }
done
test -f "$DB"
curl -fsS --connect-timeout 3 --max-time 15 \
  -o /dev/null http://127.0.0.1:8000/api/catalog

echo "===== FETCH EXACT V38 RESEARCH BUILD INTO DETACHED WORKTREE ====="
cd "$ROOT"
test -z "$(git status --porcelain)"
git fetch origin "$REF"
test "$(git rev-parse FETCH_HEAD)" = "$TARGET"
git merge-base --is-ancestor HEAD FETCH_HEAD
git merge --ff-only FETCH_HEAD
test "$(git rev-parse HEAD)" = "$TARGET"
.venv/bin/python -c 'import requests,numpy'
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1

echo "===== V39 FORECAST AUDITS MUST BE MAKING PROGRESS ====="
.venv/bin/python -m research.v38_v39_host_gate --db "$DB"

echo "===== WAIT UP TO FOUR MINUTES FOR SAFE CPU HEADROOM ====="
# Low CPU headroom can lag briefly behind a healthy V39 worker.
# Wait without changing any service, CPU threshold, or research scheduling.
# Exit safely if the audit worker stops progressing during this wait.
READY=0
for attempt in $(seq 1 13); do
  echo "CPU admission check $attempt/13"
  if .venv/bin/python -m research.v38_shadow_canary_preflight --db "$DB"; then
    READY=1
    break
  fi
  if [ "$attempt" -eq 13 ]; then
    break
  fi
  .venv/bin/python -m research.v38_v39_host_gate --db "$DB" || {
    echo "STOP: V39 audit backlog failed readiness gate" >&2
    exit 2
  }
  sleep 20
done
if [ "$READY" -ne 1 ]; then
  echo "STOP: collector or CPU never passed the unchanged safe threshold" >&2
  exit 2
fi

echo "===== REAL FIVE-MODEL READ-ONLY BENCHMARK ====="
OUT=$(mktemp /tmp/torn-fren-v38-readonly.XXXXXX)
trap 'rm -f "$OUT"' EXIT
nice -n 19 timeout 190s .venv/bin/python \
  -m research.v38_readonly_resource_probe \
  --db "$DB" --timeout 25 --budget 150 | tee "$OUT"

.venv/bin/python - "$OUT" <<'PY'
import json,sys
with open(sys.argv[1],encoding="utf-8") as source:
    r=json.load(source)
items=r.get("items",[])
unsafe={"WORKER_TIMEOUT","WORKER_ERROR","SKIPPED_BUDGET",
        "COLLECTOR_STALE_OR_NO_HEARTBEAT","FUTURE_RECORDS_PRESENT",
        "INVALID_RESULT","MISSING_STATUS","UNSUPPORTED"}
bad=[x for x in items if x.get("status") in unsafe
     or str(x.get("status","")).endswith("_ERROR")]
if len(items)!=5 or r.get("tested_count")!=5 or bad:
    raise SystemExit(f"STOP: five-model benchmark unsafe/incomplete: {bad}")
if float(r.get("total_elapsed_seconds",999))>150:
    raise SystemExit("STOP: five-model work exceeds approved budget")
print("FIVE-MODEL READ-ONLY BENCHMARK ACCEPTED;",
      "proposals",r.get("proposal_count"),"/5")
PY

echo "===== RECHECK SOURCE, LOAD, AUDIT QUEUE AND PUBLIC WEBSITE ====="
.venv/bin/python -m research.v38_shadow_canary_preflight --db "$DB"
.venv/bin/python -m research.v38_v39_host_gate --db "$DB"
curl -fsS --connect-timeout 3 --max-time 15 \
  -o /dev/null http://127.0.0.1:8000/api/catalog
test "$(git -C /opt/torn-fren rev-parse HEAD)" = "$V39_PROD_SHA"

echo "===== ENABLE ISOLATED 25%-CPU PRIVATE RESEARCH ONLY ====="
sudo install -d -m 700 -o ubuntu -g ubuntu /var/lib/torn-fren-v38
sudo install -m 644 deploy/systemd/torn-fren-v38-private-shadow.service \
  /etc/systemd/system/torn-fren-v38-private-shadow.service
sudo install -m 644 deploy/systemd/torn-fren-v38-private-shadow.timer \
  /etc/systemd/system/torn-fren-v38-private-shadow.timer
sudo systemctl daemon-reload
sudo systemd-analyze verify \
  /etc/systemd/system/torn-fren-v38-private-shadow.service \
  /etc/systemd/system/torn-fren-v38-private-shadow.timer
sudo systemctl enable --now torn-fren-v38-private-shadow.timer

echo "===== FINAL STATUS ====="
systemctl is-active torn-fren-poller.service torn-fren-web.service \
  torn-fren-bot.service torn-fren-routine-audit.timer \
  torn-fren-gap-recovery.timer torn-fren-v38-private-shadow.timer
systemctl list-timers --all torn-fren-v38-private-shadow.timer
echo "V38 PRIVATE FIVE-MODEL CANARY ARMED; no public website changes."
echo "First tick may report SOURCE_BOOTSTRAP until the history cursor catches up."
echo "Japan Xanax continues its separate existing shadow capture."
