#!/usr/bin/env bash
# READ ONLY. No removals, no systemd changes; all active sites are protected.
set -euo pipefail
echo 'TORN_FREN_VM_STORAGE_SERVICE_INVENTORY_READ_ONLY'
date -u '+UTC %Y-%m-%dT%H:%M:%SZ'
echo '===== DISK CAPACITY / INODES ====='
df -h / /home /var 2>/dev/null || df -h /
df -i / 2>/dev/null || true
echo '===== RUNNING SERVICES (names only) ====='
systemctl list-units --type=service --state=running --no-pager --no-legend |
  awk '{print $1}' | grep -E 'torn|nginx|caddy|apache|docker|postgres|sqlite|redis|github|runner' || true
echo '===== RESEARCH AND PRODUCTION TIMERS (unit names only) ====='
systemctl list-timers --all --no-pager --no-legend |
  grep -E 'torn|research|forecast' || true
echo '===== WEB CONFIG ENTRY NAMES ONLY (do not dump secrets) ====='
find /etc/nginx/sites-enabled -maxdepth 1 -mindepth 1 -printf '%f -> %l\n' 2>/dev/null || true
echo '===== CONFIGURED TORN SYSTEMD UNITS (unit names only) ====='
systemctl list-unit-files --no-pager --no-legend | grep -E '^torn-fren|^actions.runner' || true
echo '===== ESTIMATED STORAGE (metadata only) ====='
for d in /opt/torn-fren /home/ubuntu/torn-fren-v38-probe \
         /home/ubuntu/torn-fren-private-models \
         /var/lib/torn-fren-research /var/lib/torn-fren-research-runner \
         /var/log/journal /home/ubuntu; do
  if [[ -d "$d" ]]; then
    sudo -n du -sh -- "$d" 2>/dev/null || true
  fi
done
echo '===== HOME TOP-LEVEL DIRECTORY SIZES (metadata only) ====='
find /home/ubuntu -mindepth 1 -maxdepth 1 -type d -print0 |
  while IFS= read -r -d '' d; do
    sudo -n du -sh -- "$d" 2>/dev/null || true
  done | sort -h | tail -n 35
echo '===== SQLITE DATABASE FILE SIZES, NOT CONTENT ====='
for f in /opt/torn-fren/data/stock_history.db \
         /var/lib/torn-fren-research/stock_history_research.db \
         /var/lib/torn-fren-research/stock_history_forward.db; do
  if [[ -f "$f" ]]; then
    stat -c '%n bytes=%s mode=%a owner=%U group=%G' -- "$f"
  fi
done
echo 'INVENTORY_COMPLETE_NO_DELETES'
