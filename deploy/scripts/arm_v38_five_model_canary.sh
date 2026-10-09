#!/usr/bin/env bash
# Run only AFTER v39 CPU release has been healthy and monitored >=30m.
# Usage: bash arm_v38_five_model_canary.sh <exact-V38-research-SHA>
# This is isolated SHADOW evidence; no player-facing routes or game actions.
set -euo pipefail
V39_PROD_SHA="e9ba974c96553ea36f31951b94901b7379b22624"
REF="research/v38-full-roster-live-prep-20261009"
TARGET="${1:-}"
ROOT="/home/ubuntu/torn-fren-v38-probe"
if [[ ! "$TARGET" =~ ^[0-9a-f]{40}$ ]]; then
  echo "STOP: exact CI-passing research SHA required" >&2;exit 2
fi
test "$(git -C /opt/torn-fren rev-parse HEAD)" = "$V39_PROD_SHA"
test "$(systemctl is-active torn-fren-poller.service)" = active
test "$(systemctl is-active torn-fren-web.service)" = active
test "$(systemctl is-active torn-fren-routine-audit.timer)" = active
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

echo "===== CPU AND VERIFIED COLLECTOR ADMISSION ====="
.venv/bin/python -m research.v38_shadow_canary_preflight \
  --db /var/lib/torn-fren/stock_history.db

echo "===== RUN ACTUAL FIVE ORIGINAL MODELS READ-ONLY ====="
OUT=$(mktemp /tmp/torn-fren-v38-readonly.XXXXXX)
trap 'rm -f "$OUT"' EXIT
nice -n 19 timeout 120s .venv/bin/python \
  -m research.v38_readonly_resource_probe \
  --db /var/lib/torn-fren/stock_history.db \
  --timeout 9 --budget 48 | tee "$OUT"

.venv/bin/python - "$OUT" <<'PY'
import json,sys
r=json.load(open(sys.argv[1],encoding="utf-8"))
items=r["items"]
bad=[x for x in items if x["status"] in (
  "WORKER_TIMEOUT","WORKER_ERROR","SKIPPED_BUDGET",
  "COLLECTOR_STALE_OR_NO_HEARTBEAT","FUTURE_RECORDS_PRESENT")]
if len(items)!=5 or r.get("tested_count")!=5 or bad:
    raise SystemExit(f"STOP: canary workload not reliable: {bad}")
print("FIVE-WORKER BENCHMARK ACCEPTED; original model abstentions are allowed.")
PY

echo "===== INSTALL ISOLATED RESEARCH SIDECAR TIMER ONLY ====="
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
echo "PRIVATE 5/21 FLOWER/PLUSHIE SHADOW TIMER ENABLED."
echo "Japan Xanax remains on existing independent V37 research capture."
systemctl is-active torn-fren-poller.service torn-fren-web.service \
  torn-fren-v38-private-shadow.timer torn-fren-routine-audit.timer
