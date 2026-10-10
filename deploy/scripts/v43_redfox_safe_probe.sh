#!/usr/bin/env bash
# Read-only bounded Red Fox diagnostic, NEVER a production deployment.
# Pauses ONLY the private research timer during the diagnostic.
set -euo pipefail
ROOT=/home/ubuntu/torn-fren-v38-probe
PY="$ROOT/.venv/bin/python"
STOCK=/opt/torn-fren/data/stock_history.db
SVC=torn-fren-v38-private-shadow.service
TIMER=torn-fren-v38-private-shadow.timer
test "$(id -un)" = ubuntu
test -f "$STOCK"
test -x "$PY"
test -z "$(git -C "$ROOT" status --porcelain)"
for s in torn-fren-poller torn-fren-web torn-fren-bot; do
  systemctl is-active --quiet "$s.service" || { echo "STOP: $s down."; exit 1; }
done
systemctl is-active --quiet "$TIMER"
sudo systemctl stop "$TIMER"
trap 'sudo systemctl start torn-fren-v38-private-shadow.timer >/dev/null 2>&1 || true' EXIT
for n in $(seq 1 245); do
  if ! systemctl is-active --quiet "$SVC"; then break; fi
  sleep 1
done
if systemctl is-active --quiet "$SVC"; then
  echo "STOP: old research job still running."
  exit 1
fi
echo "Read-only Red Fox single-tick probe, full 25% quota and 1 GiB cap."
cd "$ROOT"
# systemd-run --wait places the benchmark in an isolated resource-limited
# service; no stock writes, no credentials, no public web changes.
NOW=$(date +%s)
sudo systemd-run --unit=torn-fren-v43-redfox-probe \
  --collect --wait --pipe \
  --working-directory="$ROOT" \
  -p CPUQuota=25% -p MemoryMax=1073741824 \
  -p Nice=19 -p TimeoutStartSec=100 \
  "$PY" -m research.v38_red_fox_single_tick \
  --db "$STOCK" --country uni --item "Red Fox Plushie" --now "$NOW"
echo "Protected probe finished. Inspect displayed status/time before scheduling."
