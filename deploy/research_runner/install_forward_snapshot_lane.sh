#!/usr/bin/env bash
# Distinct, 14-day sanitized forward snapshot: retains existing 45-day archive.
# Owner-only opt-in. Never touches any production or existing snapshot units.
set -euo pipefail
if [[ "$#" -gt 1 || ( "$#" == 1 && "$1" != "--apply" ) ]]; then
  echo "USAGE: bash install_forward_snapshot_lane.sh [--apply]" >&2
  exit 2
fi
[[ "$(id -un)" == ubuntu ]] || { echo "STOP: run as ubuntu"; exit 1; }
sudo -n true || { echo "STOP: ubuntu sudo authorization required"; exit 1; }

SRC=/opt/torn-fren/data/stock_history.db
ROSTER=/home/ubuntu/torn-fren-private-models/v160_stage/pinned/research/v38_roster.json
BASE=/var/lib/torn-fren-research
RUNNER=tornresearch
OUT="$BASE/stock_history_forward.db"
EXPORTER=/usr/local/lib/torn-fren-research/export_forward_snapshot.py
OLD_TIMER=torn-fren-research-snapshot.timer
OLD_SERVICE=torn-fren-research-snapshot.service
TIMER=torn-fren-research-forward-snapshot.timer
SERVICE=torn-fren-research-forward-snapshot.service
SERVICE_PATH=/etc/systemd/system/$SERVICE
TIMER_PATH=/etc/systemd/system/$TIMER
REPO=/home/ubuntu/torn-fren-v38-probe
EXPORTER_SHA=d2fc563c29cb800bf9cadb70e7953865f0190851
PINNED_PATH=deploy/research_runner/export_snapshot.py
test -r "$SRC" && test -r "$ROSTER" && test -r "$BASE/stock_history_research.db" || {
  echo "STOP: missing source, roster, or old research archive"; exit 1; }
test ! -L "$SRC" && test ! -L "$OUT" || {
  echo "STOP: unexpected collector or forward snapshot symlink"; exit 1; }
systemctl is-active --quiet "$OLD_TIMER" || {
  echo "STOP: existing 45-day archive timer must remain active"; exit 1; }
sudo -u "$RUNNER" test -r "$BASE/stock_history_research.db" || {
  echo "STOP: research user cannot read old sanitized archive"; exit 1; }
if sudo -u "$RUNNER" test -r "$SRC" ||
   sudo -u "$RUNNER" test -r "$ROSTER"; then
  echo "STOP: research user has unsafe collector/private stage access"; exit 1; fi
systemctl cat "$OLD_SERVICE" | grep -Fq 'CPUQuota=40%' || {
  echo "STOP: old research exporter CPU limit absent"; exit 1; }
systemctl cat "$OLD_SERVICE" | grep -Fq 'MemoryMax=640M' || {
  echo "STOP: old research exporter memory limit absent"; exit 1; }
[[ "$(stat -c %U "$BASE")" == ubuntu ]] || {
  echo "STOP: unexpected research directory owner"; exit 1; }
[[ "$(stat -c %G "$BASE")" == tornfren-research ]] || {
  echo "STOP: unexpected research directory group"; exit 1; }

git -C "$REPO" cat-file -e "$EXPORTER_SHA^{commit}" || {
  echo "STOP: pinned exporter commit unavailable; fetch public research branch"; exit 1; }
TMP=$(mktemp)
SCRATCH=$(mktemp -d "$BASE/.forward-preflight.XXXXXXXX")
SVC=$(mktemp)
TMR=$(mktemp)
trap 'rm -f "$TMP" "$SVC" "$TMR"; rm -f "$SCRATCH/snapshot.db"; rmdir "$SCRATCH" 2>/dev/null || true' EXIT
git -C "$REPO" show "$EXPORTER_SHA:$PINNED_PATH" > "$TMP"
python3 -B "$TMP" --help >/dev/null
echo "===== VERIFY SANITIZED 14-DAY FORWARD SOURCE OUTSIDE SERVICE ====="
python3 -B "$TMP" --source "$SRC" --roster "$ROSTER" \
  --output "$SCRATCH/snapshot.db" --days 14
python3 -B - "$SCRATCH/snapshot.db" <<'PREFLIGHT'
import sqlite3,sys
from pathlib import Path
p=Path(sys.argv[1]).resolve(strict=True)
with sqlite3.connect(p.as_uri()+"?mode=ro",uri=True) as c:
    c.execute("PRAGMA query_only=ON")
    m=dict(c.execute("SELECT key,value FROM research_metadata"))
    assert m.get("sanitized_stock_only")=="true"
    assert m.get("roster_size")=="24"
    assert m.get("heartbeat_provider_field_present")=="true"
    assert c.execute("SELECT COUNT(*) FROM poll_heartbeats WHERE source IS NOT NULL").fetchone()[0]>0
    assert c.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    cols={r[1] for r in c.execute("PRAGMA table_info(poll_heartbeats)")}
    assert "id" in cols and "source" in cols
    c.execute("SELECT timestamp,source FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1 ORDER BY timestamp,id LIMIT 1").fetchall()
print("PASS: sanitized forward data and independent provider evidence")
PREFLIGHT

cat > "$SVC" <<'SERVICE_UNIT'
[Unit]
Description=TORN-FREN isolated 14-day prospective forward stock snapshot
After=local-fs.target
ConditionPathExists=/opt/torn-fren/data/stock_history.db

[Service]
Type=oneshot
User=ubuntu
Group=tornfren-research
UMask=0027
ExecStart=/usr/bin/python3 -B /usr/local/lib/torn-fren-research/export_forward_snapshot.py --source /opt/torn-fren/data/stock_history.db --roster /home/ubuntu/torn-fren-private-models/v160_stage/pinned/research/v38_roster.json --output /var/lib/torn-fren-research/stock_history_forward.db --days 14
Nice=19
IOSchedulingClass=idle
CPUQuota=40%
MemoryMax=640M
TasksMax=32
TimeoutStartSec=120
NoNewPrivileges=yes
PrivateTmp=yes
PrivateDevices=yes
PrivateNetwork=yes
ProtectSystem=strict
ProtectHome=read-only
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
LockPersonality=yes
RestrictSUIDSGID=yes
ReadWritePaths=/var/lib/torn-fren-research
InaccessiblePaths=/var/lib/torn-fren-v38
CapabilityBoundingSet=
AmbientCapabilities=
SERVICE_UNIT
cat > "$TMR" <<'TIMER_UNIT'
[Unit]
Description=Refresh isolated sanitized forward stock evidence approximately every 90 seconds

[Timer]
OnBootSec=2min
OnUnitInactiveSec=90s
AccuracySec=5s
RandomizedDelaySec=0
Unit=torn-fren-research-forward-snapshot.service
Persistent=false

[Install]
WantedBy=timers.target
TIMER_UNIT
for pair in "$SERVICE_PATH:$SVC" "$TIMER_PATH:$TMR"; do
  dest=${pair%%:*}; candidate=${pair#*:}
  if sudo test -e "$dest" && ! sudo cmp -s "$dest" "$candidate"; then
    echo "STOP: existing service/timer differs: $dest"; exit 1
  fi
done
if sudo test -e "$EXPORTER" && ! sudo cmp -s "$EXPORTER" "$TMP"; then
  echo "STOP: unexpected separate forward exporter exists"; exit 1
fi
echo "DRY_RUN_OK: existing 45-day archive, websites, collector and V160 remain unchanged."
echo "Prepared independent 14-day forward snapshot (90-second timer), CPU quota 40%, memory 640 MiB."
if [[ "$#" == 0 ]]; then
  echo "No installation performed. Repeat with --apply to install only separate forward units."
  exit 0
fi
echo "===== APPLY INDEPENDENT FORWARD RESEARCH UNITS ====="
sudo install -o root -g root -m 0644 "$TMP" "$EXPORTER"
sudo install -o root -g root -m 0644 "$SVC" "$SERVICE_PATH"
sudo install -o root -g root -m 0644 "$TMR" "$TIMER_PATH"
sudo systemctl daemon-reload
# Prove the full systemd sandbox works BEFORE enabling frequent work.
if ! sudo systemctl start "$SERVICE"; then
  echo "STOP: new sandboxed 14-day exporter failed, no timer enabled."
  echo "Read journalctl -u $SERVICE. Existing 45-day research archive unchanged."
  exit 1
fi
python3 -B - "$OUT" <<'VALIDATE'
import sqlite3,sys,time
from pathlib import Path
p=Path(sys.argv[1]).resolve(strict=True)
with sqlite3.connect(p.as_uri()+"?mode=ro",uri=True) as c:
    c.execute("PRAGMA query_only=ON")
    m=dict(c.execute("SELECT key,value FROM research_metadata"))
    assert m.get("sanitized_stock_only")=="true" and m.get("roster_size")=="24"
    assert m.get("history_days")=="14"
    assert m.get("heartbeat_provider_field_present")=="true"
    assert int(time.time())-int(m["source_cutoff_epoch"])<160
    assert c.execute("SELECT COUNT(*) FROM poll_heartbeats WHERE source IS NOT NULL").fetchone()[0]>0
    assert c.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    c.execute("SELECT timestamp,source FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1 ORDER BY timestamp,id LIMIT 1").fetchall()
print("PASS: independently sandboxed forward snapshot is fresh")
VALIDATE
sudo -u "$RUNNER" test -r "$OUT" || {
  echo "STOP: private runner cannot access sanitized fast snapshot"; exit 1; }
if sudo -u "$RUNNER" test -r "$SRC"; then
  echo "STOP: isolation violation; do not enable timer"; exit 1; fi
sudo systemctl enable --now "$TIMER"
systemctl is-active --quiet "$TIMER" || {
  echo "STOP: new forward timer failed to activate"; exit 1; }
systemctl is-active --quiet "$OLD_TIMER" || {
  echo "STOP: existing historical archive timer unexpectedly inactive"; exit 1; }
echo "FORWARD_SNAPSHOT_ACTIVE_ONLY: 14-day isolated read-only sanitized snapshot on 90s timer."
echo "Original 45-day archive + all production/website units unchanged."
