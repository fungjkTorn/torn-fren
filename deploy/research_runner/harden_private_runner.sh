#!/usr/bin/env bash
# Harden a PRIVATE-repository GitHub Actions runner before its first start.
set -euo pipefail
[[ "$(id -u)" == 0 ]] || { echo "STOP: run with sudo"; exit 1; }
UNIT="$1"
[[ "$UNIT" =~ ^actions\.runner\.[A-Za-z0-9_.-]+\.service$ ]] || {
 echo "STOP: specify a GitHub Actions runner unit"; exit 1; }
WORK=/var/lib/torn-fren-research-runner
DATA=/var/lib/torn-fren-research/stock_history_research.db
[[ -d "$WORK" && -r "$DATA" ]] || {
 echo "STOP: separate runner home or sanitized snapshot missing"; exit 1; }
systemctl cat "$UNIT" >/dev/null || {
 echo "STOP: runner service not installed"; exit 1; }
if systemctl is-active --quiet "$UNIT"; then
 echo "STOP: runner is active. Stop it before sandbox configuration."; exit 1
fi
test "$(systemctl show "$UNIT" -p User --value)" = tornresearch || {
 echo "STOP: runner systemd service is not configured as tornresearch"; exit 1; }
mkdir -p "/etc/systemd/system/$UNIT.d"
cat > "/etc/systemd/system/$UNIT.d/90-isolated-research.conf" <<'OVERRIDE'
[Service]
User=tornresearch
Group=tornfren-research
UMask=0077
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
ProtectClock=yes
ProtectHostname=yes
LockPersonality=yes
RestrictSUIDSGID=yes
RestrictRealtime=yes
RestrictNamespaces=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ReadWritePaths=/var/lib/torn-fren-research-runner
ReadOnlyPaths=/var/lib/torn-fren-research
InaccessiblePaths=/opt/torn-fren/data /home/ubuntu /var/lib/torn-fren-v38
CapabilityBoundingSet=
AmbientCapabilities=
TasksMax=128
CPUQuota=150%
MemoryMax=3G
OVERRIDE
systemctl daemon-reload
test "$(systemctl show "$UNIT" -p ProtectSystem --value)" = strict || {
 echo "STOP: sandbox not loaded by systemd"; exit 1; }
test "$(systemctl show "$UNIT" -p User --value)" = tornresearch || {
 echo "STOP: sandbox UID not loaded"; exit 1; }
echo "SUCCESS: private GitHub runner service hardened. Now start using sudo ./svc.sh start."
echo "Never register this runner with the public torn-fren repository."
