#!/usr/bin/env bash
# Research-only VM snapshot-timer cadence tuning for real five-minute forward issues.
# NEVER alter the production collector, research exporter code, or VM ACLs.
# Default: diagnostics only. --apply deliberately enables the bounded timer override.
set -euo pipefail
[[ "$#" -eq 0 || ( "$#" -eq 1 && "$1" == "--apply" ) ]] || {
  echo "USAGE: bash tune_snapshot_for_forward.sh [--apply]" >&2; exit 2; }
APPLY=0
[[ $# == 0 ]] || APPLY=1
[[ "$(id -un)" == ubuntu ]] || { echo "STOP: ubuntu account required"; exit 1; }

TIMER=torn-fren-research-snapshot.timer
UNIT=torn-fren-research-snapshot.service
SOURCE=/opt/torn-fren/data/stock_history.db
SANITIZED=/var/lib/torn-fren-research/stock_history_research.db
RESEARCH=/var/lib/torn-fren-research
OVERRIDE=/etc/systemd/system/torn-fren-research-snapshot.timer.d/40-forward-freshness.conf

command -v sudo >/dev/null || { echo "STOP: sudo required"; exit 1; }
sudo -n true || { echo "STOP: sudo authorization required"; exit 1; }
test -r "$SOURCE" || { echo "STOP: collector-owner cannot read source"; exit 1; }
test -r "$SANITIZED" || { echo "STOP: sanitized snapshot missing"; exit 1; }
test -d "$RESEARCH" && test ! -L "$RESEARCH" || {
  echo "STOP: unexpected research directory"; exit 1; }
test ! -L "$SANITIZED" || { echo "STOP: sanitized output is symlink"; exit 1; }
systemctl is-active --quiet "$TIMER" || {
  echo "STOP: sanitized snapshot timer is not active"; exit 1; }
test "$(systemctl show "$UNIT" -p User --value)" = ubuntu || {
  echo "STOP: sanitized exporter service identity changed"; exit 1; }
test "$(systemctl show "$UNIT" -p Group --value)" = tornfren-research || {
  echo "STOP: sanitized exporter group changed"; exit 1; }
# The installed exporter is intentionally root-owned, and collector DB
# access remains available only to ubuntu, not the GitHub research runner.
systemctl cat "$UNIT" | grep -Fq '/usr/local/lib/torn-fren-research/export_snapshot.py' || {
  echo "STOP: sanitized exporter command differs from approved unit"; exit 1; }
systemctl cat "$UNIT" | grep -Fq 'CPUQuota=40%' || {
  echo "STOP: export CPU protection unavailable"; exit 1; }
systemctl cat "$UNIT" | grep -Fq 'MemoryMax=640M' || {
  echo "STOP: export memory protection unavailable"; exit 1; }
systemctl cat "$UNIT" | grep -Fq 'ReadWritePaths=/var/lib/torn-fren-research' || {
  echo "STOP: separate output-directory sandbox missing"; exit 1; }
sudo -n -u tornresearch test -r "$SANITIZED" || {
  echo "STOP: restricted runner cannot read sanitized snapshot"; exit 1; }
if sudo -n -u tornresearch test -r "$SOURCE"; then
  echo "STOP: runner can read live collector! DO NOT PROCEED"; exit 1
fi
if sudo -n -u tornresearch test -r \
  /home/ubuntu/torn-fren-private-models/v160_stage/pinned/research/v38_roster.json; then
  echo "STOP: restricted runner can read private V160 stage"; exit 1
fi
echo "===== EXISTING RESEARCH EXPORTER / TIMER ====="
systemctl show "$UNIT" -p ActiveState -p Result -p User -p Group -p MemoryMax -p CPUQuotaPerSecUSec --no-pager
systemctl list-timers --all "$TIMER" --no-pager
systemctl show "$TIMER" -p OnUnitInactiveUSec -p AccuracyUSec --no-pager
if (( !APPLY )); then
  echo "DRY_RUN_OK: only the RESEARCH timer can be tuned to 2min cadence."
  echo "Run again with --apply only after inspecting the checks above."
  exit 0
fi
sudo install -d -o root -g root -m 0755 "$(dirname "$OVERRIDE")"
# Refuse to clobber an existing unexpected override; idempotent if exact.
TEMPLATE=$(mktemp)
trap 'rm -f "$TEMPLATE"' EXIT
cat > "$TEMPLATE" <<'TIMER_OVERRIDE'
[Timer]
# Only sanitized snapshots. Preserve the base unit, exporter and ACLs.
OnUnitInactiveSec=
OnUnitInactiveSec=2min
AccuracySec=10s
RandomizedDelaySec=0
TIMER_OVERRIDE
if sudo test -e "$OVERRIDE"; then
  sudo cmp -s "$TEMPLATE" "$OVERRIDE" || {
    echo "STOP: override exists with different content; investigate manually"; exit 1; }
else
  sudo install -o root -g root -m 0644 "$TEMPLATE" "$OVERRIDE"
fi
sudo systemctl daemon-reload
# Restart ONLY the RESEARCH timer. Do not stop exporter if it is already running.
sudo systemctl restart "$TIMER"
systemctl is-active --quiet "$TIMER" || {
  echo "STOP: research snapshot timer did not restart"; exit 1; }
systemctl cat "$TIMER" | grep -Fq 'OnUnitInactiveSec=2min' || {
  echo "STOP: 2-minute timer override not loaded"; exit 1; }
sudo -n -u tornresearch test ! -r "$SOURCE" || {
  echo "STOP: isolation changed unexpectedly"; exit 1; }
echo "===== RESEARCH TIMER AFTER APPLY ====="
systemctl list-timers --all "$TIMER" --no-pager
systemctl show "$TIMER" -p OnUnitInactiveUSec -p AccuracyUSec --no-pager
echo "RESEARCH_TIMER_UPDATED_ONLY: sanitized 24-item copy every ~2min after exporter completion."
echo "Watch exporter CPU/timeouts and forward status. No live website/collector changes."
