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
EXPORTER=/usr/local/lib/torn-fren-research/export_snapshot.py
ROSTER=/home/ubuntu/torn-fren-private-models/v160_stage/pinned/research/v38_roster.json
WORK=/home/ubuntu/torn-fren-v38-probe
# Exact tested research exporter with optional nonsecret poll provider label.
EXPORTER_PIN=953760eaa1ee8d1813f516183f0d3f2b4aa9b19c

command -v sudo >/dev/null || { echo "STOP: sudo required"; exit 1; }
sudo -n true || { echo "STOP: sudo authorization required"; exit 1; }
test -r "$SOURCE" || { echo "STOP: collector-owner cannot read source"; exit 1; }
test -r "$SANITIZED" || { echo "STOP: sanitized snapshot missing"; exit 1; }
test -r "$ROSTER" && test -r "$EXPORTER" || {
  echo "STOP: pinned research roster or installed exporter not readable"; exit 1; }
test "$(stat -c %U "$EXPORTER")" = root || {
  echo "STOP: unexpected installed exporter owner"; exit 1; }
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
# Preflight revised SANITIZED EXPORTER before touching existing service/timer.
# This uses a separate private scratch output, never the collector or live
# research snapshot, so a validation failure leaves current operations intact.
test "$(git -C "$WORK" rev-parse --show-toplevel)" = "$WORK" || {
  echo "STOP: unrecognized research Git checkout"; exit 1; }
git -C "$WORK" cat-file -e "$EXPORTER_PIN^{commit}" || {
  echo "STOP: fetch approved research commit before applying"; exit 1; }
CANDIDATE=$(mktemp --suffix=.py)
SCRATCH=$(mktemp -d "$RESEARCH/.forward-snapshot-validation.XXXXXXXX")
BACKUP=$(mktemp)
trap 'rm -f "$CANDIDATE" "$BACKUP"; rm -f "$SCRATCH/snapshot.db"; rmdir "$SCRATCH" 2>/dev/null || true' EXIT
git -C "$WORK" show "$EXPORTER_PIN:deploy/research_runner/export_snapshot.py" > "$CANDIDATE"
python3 -B "$CANDIDATE" --help >/dev/null
python3 -B "$CANDIDATE" --source "$SOURCE" --roster "$ROSTER" \
  --output "$SCRATCH/snapshot.db" --days 14
python3 -B - "$SCRATCH/snapshot.db" <<'CHECK_PROVIDER'
import sqlite3,sys
from pathlib import Path
p=Path(sys.argv[1]).resolve(strict=True)
with sqlite3.connect(p.as_uri()+"?mode=ro",uri=True) as cx:
    cx.execute("PRAGMA query_only=ON")
    meta=dict(cx.execute("SELECT key,value FROM research_metadata"))
    assert meta["sanitized_stock_only"]=="true"
    assert meta["roster_size"]=="24"
    assert meta.get("heartbeat_provider_field_present")=="true", (
        "STOP: live collector has no poll provider evidence; do not claim restock identity")
    assert cx.execute("SELECT COUNT(*) FROM poll_heartbeats WHERE source IS NOT NULL").fetchone()[0]>0
print("PASS: sanitized-provider evidence and read-only preflight succeeded")
CHECK_PROVIDER
# Only after verified temporary export: safely replace root-owned sanitizer.
cp -- "$EXPORTER" "$BACKUP"
sudo install -o root -g root -m 0644 "$CANDIDATE" "$EXPORTER"
if ! sudo systemctl start "$UNIT"; then
  sudo install -o root -g root -m 0644 "$BACKUP" "$EXPORTER"
  echo "STOP: full exporter trial failed; previous executable restored"; exit 1
fi
if [[ "$(systemctl show "$UNIT" -p Result --value)" != success ]]; then
  sudo install -o root -g root -m 0644 "$BACKUP" "$EXPORTER"
  echo "STOP: full exporter did not complete; previous executable restored"; exit 1
fi
python3 -B - "$SANITIZED" <<'VERIFY_EXPORT'
import sqlite3,sys
from pathlib import Path
p=Path(sys.argv[1]).resolve(strict=True)
with sqlite3.connect(p.as_uri()+"?mode=ro",uri=True) as cx:
    cx.execute("PRAGMA query_only=ON")
    md=dict(cx.execute("SELECT key,value FROM research_metadata"))
    assert md.get("sanitized_stock_only")=="true"
    assert md.get("heartbeat_provider_field_present")=="true"
    assert cx.execute("SELECT COUNT(*) FROM poll_heartbeats WHERE source IS NOT NULL").fetchone()[0]>0
print("PASS: full 45-day sanitized snapshot now retains provider evidence")
VERIFY_EXPORT
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
