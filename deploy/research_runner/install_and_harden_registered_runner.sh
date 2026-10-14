#!/usr/bin/env bash
# Install but DO NOT START the GitHub Actions runner service; enforce the
# pretested systemd production-data sandbox before the first run.
# Corrects previous manual instructions: .runner is under mode-700 directory,
# so ubuntu needs sudo to inspect it; .service is created by svc.sh install.
set -euo pipefail
[[ "$(id -un)" == ubuntu ]] || { echo "STOP: run as ubuntu"; exit 1; }
sudo -n true || { echo "STOP: sudo unavailable"; exit 1; }

RUNNER=/var/lib/torn-fren-research-runner
WORK=/home/ubuntu/torn-fren-v38-probe
LIVE=/opt/torn-fren/data/stock_history.db
SNAP=/var/lib/torn-fren-research/stock_history_research.db
ROSTER=/home/ubuntu/torn-fren-private-models/v160_stage/pinned/research/v38_roster.json
PIN=50b3b302496ebc069e05e0e95b8d2de8f5a9f70b
PRIVATE_REPO=https://github.com/fungjktorn/torn-fren-research-private

echo "===== VERIFY REGISTERED RUNNER AND ISOLATION ====="
test "$(uname -m)" = aarch64 || { echo "STOP: wrong VM CPU"; exit 1; }
sudo -n test -f "$RUNNER/.runner" || {
  echo "STOP: GitHub runner registration file missing"; exit 1;
}
sudo -n test -x "$RUNNER/svc.sh" || {
  echo "STOP: GitHub runner service installer not extracted"; exit 1;
}
sudo -n test -x "$RUNNER/bin/Runner.Listener" || {
  echo "STOP: GitHub Actions ARM64 runner executable missing"; exit 1;
}
test "$(stat -c %U -- "$RUNNER")" = tornresearch || {
  echo "STOP: research runner directory owner mismatch"; exit 1;
}
sudo -n python3 - "$RUNNER/.runner" "$PRIVATE_REPO" <<'VERIFY_SCOPE'
import json,sys
from pathlib import Path
data=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
actual=str(data.get("gitHubUrl","")).rstrip("/").lower()
if actual != sys.argv[2]:
    raise SystemExit("STOP: runner is not registered to exact PRIVATE repository")
print("PASS: GitHub runner registered to PRIVATE research repository")
VERIFY_SCOPE
sudo -n -u tornresearch test -r "$SNAP" || {
  echo "STOP: research user cannot read sanitized stock snapshot"; exit 1;
}
if sudo -n -u tornresearch test -r "$LIVE"; then
  echo "STOP: research account can read the LIVE collector"; exit 1
fi
if sudo -n -u tornresearch test -r "$ROSTER"; then
  echo "STOP: research account can read private model stage"; exit 1
fi
systemctl is-active --quiet torn-fren-research-snapshot.timer || {
  echo "STOP: research snapshot timer inactive"; exit 1
}
systemctl is-active --quiet torn-fren-v160-forward24.timer || {
  echo "STOP: original V160 timer inactive"; exit 1
}

echo "===== VALIDATE PINNED SECURITY SCRIPT BEFORE INSTALL ====="
test "$(git -C "$WORK" rev-parse --show-toplevel)" = "$WORK" || {
  echo "STOP: incorrect Git checkout"; exit 1;
}
TEMP=$(mktemp)
trap 'rm -f "$TEMP"' EXIT
git -C "$WORK" cat-file -e "$PIN^{commit}"
git -C "$WORK" show "$PIN:deploy/research_runner/harden_private_runner.sh" > "$TEMP"
bash -n "$TEMP"

echo "===== INSTALL SERVICE (NO START) ====="
if sudo -n test -f "$RUNNER/.service"; then
  echo "Runner service installation marker already exists; verify and harden it."
else
  # GitHub svc.sh creates .service during installation; never precheck it.
  # Running as root is required by svc.sh; it configures User=tornresearch.
  (cd "$RUNNER" && sudo -n ./svc.sh install tornresearch)
fi
sudo -n test -f "$RUNNER/.service" || {
  echo "STOP: GitHub svc.sh did not create .service"; exit 1
}
UNIT=$(sudo -n cat "$RUNNER/.service")
[[ "$UNIT" =~ ^actions\.runner\.[A-Za-z0-9_.-]+\.service$ ]] || {
  echo "STOP: unexpected service unit name"; exit 1
}
systemctl cat "$UNIT" >/dev/null || {
  echo "STOP: service unit not registered"; exit 1
}
if systemctl is-active --quiet "$UNIT"; then
  echo "STOP: service unexpectedly started; stop and investigate BEFORE hardening"
  exit 1
fi

echo "===== ENFORCE SANDBOX WHILE SERVICE REMAINS STOPPED ====="
sudo -n bash "$TEMP" "$UNIT"

echo "===== REPORT PROTECTION SETTINGS ====="
systemctl show "$UNIT" --no-pager \
  -p User -p Group -p ActiveState -p UnitFileState \
  -p ProtectSystem -p ProtectHome -p NoNewPrivileges \
  -p InaccessiblePaths -p ReadWritePaths -p IPAddressDeny \
  -p MemoryMax -p CPUQuotaPerSecUSec
test "$(systemctl show "$UNIT" -p ActiveState --value)" != active || {
  echo "STOP: runner unexpectedly active"; exit 1
}
test "$(systemctl show "$UNIT" -p ProtectSystem --value)" = strict
test "$(systemctl show "$UNIT" -p User --value)" = tornresearch
test "$(systemctl show "$UNIT" -p NoNewPrivileges --value)" = yes
echo "SUCCESS: PRIVATE GitHub runner service INSTALLED and HARDENED."
echo "Runner intentionally NOT STARTED. Verify the above settings before starting."
