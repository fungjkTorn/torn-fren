#!/usr/bin/env bash
# V47 first bounded warm-up: exact original 24-expert resolved cache.
# Usage: bash deploy/scripts/v47_online_cache_probe.sh monkey|chamois
# Does not modify V38/V44 scheduler, website, collector, bot, or existing sidecar.
set -euo pipefail
TARGET=monkey
if [ "$#" -gt 0 ]; then TARGET="$1"; fi
case "$TARGET" in monkey|chamois) ;; *) echo "Usage: $0 monkey|chamois"; exit 2 ;; esac

ROOT=/home/ubuntu/torn-fren-v38-probe
PY="$ROOT/.venv/bin/python"
DB=/opt/torn-fren/data/stock_history.db
CACHE=/var/lib/torn-fren-v47/online_expert_cache.db
UNIT="torn-fren-v47-$TARGET-first-cache"
test "$(id -un)" = ubuntu
test -x "$PY"
test -f "$DB"
test -z "$(git -C "$ROOT" status --porcelain)"
for service in torn-fren-v38-private-shadow.timer torn-fren-web.service torn-fren-poller.service torn-fren-bot.service; do
  systemctl is-active --quiet "$service" || { echo "STOP: $service inactive"; exit 1; }
done

sudo install -d -o ubuntu -g ubuntu -m 700 /var/lib/torn-fren-v47
echo "V47: cache at $CACHE; collector remains READ ONLY."
echo "Probe $TARGET under 20% CPU, 1GiB max, 115-second watchdog."
echo "This can report BUILDING_RESOLVED_EXPERT_CACHE: normal until complete."
cd "$ROOT"
sudo systemd-run --unit="$UNIT" --collect --wait --pipe \
  --working-directory="$ROOT" \
  -p User=ubuntu -p Group=ubuntu \
  -p CPUQuota=20% -p MemoryMax=1073741824 \
  -p Nice=19 -p TimeoutStartSec=115 \
  "$PY" -m research.v47_online_expert_cache \
  --db "$DB" --cache "$CACHE" --target "$TARGET" \
  --budget 40 --max-decisions 24
echo "V47 private cache probe finished; 19-model scheduler unchanged."
