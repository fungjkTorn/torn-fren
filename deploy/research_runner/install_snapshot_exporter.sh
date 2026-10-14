#!/usr/bin/env bash
# One-time, bounded, opt-in installation: sanitized FOREIGN STOCK snapshots only.
# Does not configure, install, or execute a GitHub Actions runner.
# Does not touch production site/collector/systemd units/V160 timer.
set -euo pipefail
[[ "$(id -un)" == ubuntu ]] || { echo "STOP: invoke as ubuntu user"; exit 1; }
command -v sudo >/dev/null || { echo "STOP sudo unavailable"; exit 1; }
sudo -n true || { echo "STOP: ubuntu sudo authorization needed"; exit 1; }

WORK=/home/ubuntu/torn-fren-v38-probe
SRC=/opt/torn-fren/data/stock_history.db
ROSTER=/home/ubuntu/torn-fren-private-models/v160_stage/pinned/research/v38_roster.json
BASE=/var/lib/torn-fren-research
RUNNER_HOME=/var/lib/torn-fren-research-runner
ENGINE=/usr/local/lib/torn-fren-research/export_snapshot.py
GROUP=tornfren-research
USER=tornresearch
PIN=8428b6a36e67cc4a0fc9f49b1820ef88f94b34af
UNIT=torn-fren-research-snapshot.service
TIMER=torn-fren-research-snapshot.timer

test -f "$SRC" && test -r "$SRC" || {
 echo "STOP: current stock history unreadable as ubuntu"; exit 1; }
test -r "$ROSTER" || { echo "STOP: verified 24-item roster missing"; exit 1; }
test -x "$WORK/.venv/bin/python" || { echo "STOP: research environment unavailable"; exit 1; }
test "$(git -C "$WORK" rev-parse --show-toplevel)" == "$WORK" || {
 echo "STOP: wrong worktree"; exit 1; }
systemctl is-active --quiet torn-fren-v160-forward24.timer || {
 echo "STOP: baseline forecast timer not healthy"; exit 1; }

echo "===== FETCH EXACT PINNED EXPORTED-SNAPSHOT CODE ====="
cd "$WORK"
git fetch -q origin research/v38-full-roster-live-prep-20261009
git cat-file -e "$PIN^{commit}"
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
git show "$PIN:deploy/research_runner/export_snapshot.py" > "$TMP"
python3 -B -m py_compile "$TMP" || {
 echo "STOP: snapshot export failed Python syntax check"; exit 1; }

echo "===== PREPARE SEPARATE UNPRIVILEGED RESEARCH READER ====="
if ! getent group "$GROUP" >/dev/null; then
 sudo groupadd --system "$GROUP"
fi
if ! id "$USER" >/dev/null 2>&1; then
 sudo useradd --system --create-home --home-dir "$RUNNER_HOME" \
  --gid "$GROUP" --shell /bin/bash "$USER"
fi
[[ "$(id -gn "$USER")" == "$GROUP" ]] || {
 echo "STOP research account has unexpected primary group"; exit 1; }
sudo install -d -o ubuntu -g "$GROUP" -m 2750 "$BASE"
sudo install -d -o root -g root -m 0755 /usr/local/lib/torn-fren-research
sudo install -o root -g root -m 0644 "$TMP" "$ENGINE"
sudo chmod 0700 "$RUNNER_HOME"

echo "===== INSTALL INDEPENDENT READ-ONLY SNAPSHOT TIMER ====="
SERVICE=$(mktemp)
TIMER_FILE=$(mktemp)
trap 'rm -f "$TMP" "$SERVICE" "$TIMER_FILE"' EXIT
cat > "$SERVICE" <<'SERVICE_CONTENT'
[Unit]
Description=Torn-Fren 24-item stock-history research snapshot (no gameplay)
After=local-fs.target
ConditionPathExists=/opt/torn-fren/data/stock_history.db

[Service]
Type=oneshot
User=ubuntu
Group=tornfren-research
UMask=0027
ExecStart=/usr/bin/python3 -B /usr/local/lib/torn-fren-research/export_snapshot.py --source /opt/torn-fren/data/stock_history.db --roster /home/ubuntu/torn-fren-private-models/v160_stage/pinned/research/v38_roster.json --output /var/lib/torn-fren-research/stock_history_research.db --days 45
Nice=19
IOSchedulingClass=idle
CPUQuota=40%
MemoryMax=640M
TasksMax=32
TimeoutStartSec=180
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
SERVICE_CONTENT
cat > "$TIMER_FILE" <<'TIMER_CONTENT'
[Unit]
Description=Refresh Torn-Fren research-only sanitized history

[Timer]
OnBootSec=6min
OnUnitInactiveSec=30min
AccuracySec=3min
Unit=torn-fren-research-snapshot.service
Persistent=true

[Install]
WantedBy=timers.target
TIMER_CONTENT

sudo install -o root -g root -m 0644 "$SERVICE" "/etc/systemd/system/$UNIT"
sudo install -o root -g root -m 0644 "$TIMER_FILE" "/etc/systemd/system/$TIMER"
sudo systemctl daemon-reload
sudo systemctl start "$UNIT"
test "$(systemctl show "$UNIT" -p Result --value)" = success || {
 echo "STOP research snapshot service did not complete"; exit 1; }
test -r "$BASE/stock_history_research.db" || {
 echo "STOP no sanitized output"; exit 1; }

echo "===== VERIFY LEAST-PRIVILEGE RESEARCH ACCOUNT ====="
sudo -u "$USER" test -r "$BASE/stock_history_research.db" || {
 echo "STOP separate runner cannot read sanitized snapshot"; exit 1; }
# Do not register the runner if the account can access live/source data.
if sudo -u "$USER" test -r "$SRC"; then
 echo "STOP: isolated user can read LIVE collector. Restrict its access"
 echo "before registering any private GitHub runner."
 exit 1
fi
if sudo -u "$USER" test -r "$ROSTER"; then
 echo "STOP: isolated runner can read the staged private research tree."
 exit 1
fi
sudo systemctl enable --now "$TIMER"
echo "SUCCESS: sanitized read-only 24-item stock dataset on independent timer."
echo "No GitHub runner registered; no website, collector, V160 service or API key modified."
echo "NEXT: create private GitHub repo; register a runner as $USER ONLY to that private repo."
