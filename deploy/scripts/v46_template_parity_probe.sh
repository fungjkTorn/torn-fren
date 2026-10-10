#!/usr/bin/env bash
# V46 parity and speed test vs original Monkey/Chamois replay.
# Usage: bash deploy/scripts/v46_template_parity_probe.sh monkey|chamois
# No production changes, no collector writes, research timer restored.
set -euo pipefail
TARGET="monkey"
if [ "$#" -gt 0 ]; then TARGET="$1"; fi
case "$TARGET" in monkey|chamois) ;; *) echo "Usage: $0 monkey|chamois"; exit 2 ;; esac
ROOT=/home/ubuntu/torn-fren-v38-probe
PY="$ROOT/.venv/bin/python"
STOCK=/opt/torn-fren/data/stock_history.db
SERVICE=torn-fren-v38-private-shadow.service
TIMER=torn-fren-v38-private-shadow.timer
test "$(id -un)" = ubuntu
test -x "$PY"
test -f "$STOCK"
test -z "$(git -C "$ROOT" status --porcelain)"
for s in torn-fren-web torn-fren-poller torn-fren-bot; do
  systemctl is-active --quiet "$s.service" || { echo "STOP: $s down"; exit 1; }
done
systemctl is-active --quiet "$TIMER"
sudo systemctl stop "$TIMER"
trap 'sudo systemctl start torn-fren-v38-private-shadow.timer >/dev/null 2>&1 || true' EXIT
for n in $(seq 1 245); do
  if ! systemctl is-active --quiet "$SERVICE"; then break; fi
  sleep 1
done
if systemctl is-active --quiet "$SERVICE"; then
  echo "STOP: research scheduler still working"
  exit 1
fi
cd "$ROOT"
echo "Compare original and vectorized $TARGET expert 0 on the SAME historical anchor"
sudo systemd-run --unit="torn-fren-v46-$TARGET-parity" --collect --wait --pipe \
  --working-directory="$ROOT" \
  -p CPUQuota=25% -p MemoryMax=1073741824 \
  -p Nice=19 -p TimeoutStartSec=115 \
  "$PY" -m research.v45_online_template_probe \
  --db "$STOCK" --target "$TARGET" --expert-index 0 \
  --now "$(date +%s)" --compare-fast
echo "Comparison finished; no scheduler routing changed."
