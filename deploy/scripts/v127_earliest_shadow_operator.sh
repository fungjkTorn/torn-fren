#!/usr/bin/env bash
# Guarded, opt-in, low-priority V127 research recorder staging/installer.
# Usage: bash deploy/scripts/v127_earliest_shadow_operator.sh status|smoke|enable|disable
set -euo pipefail
export SYSTEMD_PAGER=cat

ACTION="${1:-status}"
[[ "$ACTION" =~ ^(status|smoke|enable|disable)$ ]] || {
  echo "Use status|smoke|enable|disable"; exit 2;
}
[[ "$(id -un)" == "ubuntu" ]] || { echo "STOP: run as ubuntu"; exit 1; }

SERVICE=torn-fren-v127-earliest-shadow.service
TIMER=torn-fren-v127-earliest-shadow.timer
WORK=/home/ubuntu/torn-fren-v38-probe
STAGE=/home/ubuntu/torn-fren-private-models/v127_stage/pinned
COMMIT=522a41b27b9e08dc6deef0e1ac6f8fb58df07254
DB=/opt/torn-fren/data/stock_history.db
SIDE=/var/lib/torn-fren-v38
UNIT_SOURCE=deploy/systemd
UNIT_DEST=/etc/systemd/system

if [[ "$ACTION" == status ]]; then
  systemctl is-enabled "$TIMER" 2>/dev/null || true
  systemctl is-active "$TIMER" 2>/dev/null || true
  systemctl is-active torn-fren-v38-private-shadow.timer 2>/dev/null || true
  systemctl list-timers --all "$TIMER" --no-pager || true
  sudo test -f "$SIDE/v125_earliest_credible_shadow.db" \
    && sudo ls -lh "$SIDE/v125_earliest_credible_shadow.db" \
    || echo "Private V125 sidecar absent; not yet recorded"
  exit 0
fi

if [[ "$ACTION" == disable ]]; then
  sudo systemctl disable --now "$TIMER"
  echo "Disabled ONLY $TIMER; existing production/research untouched"
  systemctl is-enabled "$TIMER" || true
  exit 0
fi

cd "$WORK"
test -r "$DB" || { echo "STOP: collector source unreadable"; exit 1; }
test -d "$SIDE" || { echo "STOP: private sidecar directory absent"; exit 1; }
test -x .venv/bin/python || { echo "STOP: Python venv missing"; exit 1; }

git fetch origin research/v38-full-roster-live-prep-20261009
git cat-file -e "${COMMIT}^{commit}"

mkdir -p "$STAGE/research/plushie_champions"

for module in \
  v34_prospective_ops_audit \
  v38_snapshot_schema \
  v38_prediction_store \
  v57_exception_fingerprint \
  v60_private_snapshot_probe \
  v76_forward_research_report \
  v88_poll_state_forward_report \
  v102_restock_departure_bridge \
  v107_explicit_restock_cycle_baseline \
  v109_raw_restock_transition_event_audit \
  v110_multicycle_restock_horizon_audit \
  v123_empirical_phase_survival_challenger \
  v125_earliest_credible_shadow
do
  git show "${COMMIT}:research/${module}.py" \
    > "$STAGE/research/${module}.py"
done
for module in __init__ common
do
  git show "${COMMIT}:research/plushie_champions/${module}.py" \
    > "$STAGE/research/plushie_champions/${module}.py"
done
git show "${COMMIT}:deploy/scripts/v127_shadow_launcher.py" \
  > "$STAGE/v127_shadow_launcher.py"

PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 \
  OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  nice -n 15 timeout 120s \
  .venv/bin/python "$STAGE/v127_shadow_launcher.py" --preview

echo "Pinned V127 smoke preview succeeded; no files written by preview."
if [[ "$ACTION" == smoke ]]; then
  echo "Timer NOT installed or enabled."; exit 0;
fi

# Only an explicit 'enable' reaches here. Never override a different unit.
for name in "$SERVICE" "$TIMER"; do
  src="$UNIT_SOURCE/$name"
  target="$UNIT_DEST/$name"
  git show "${COMMIT}:deploy/systemd/$name" > "/tmp/$name.v127-checked"
  if sudo test -e "$target" && ! sudo cmp -s "/tmp/$name.v127-checked" "$target"; then
    echo "STOP: existing $name differs; refuse to overwrite"; exit 1
  fi
done

for name in "$SERVICE" "$TIMER"; do
  sudo install -o root -g root -m 0644 \
    "/tmp/$name.v127-checked" "$UNIT_DEST/$name"
done
sudo systemctl daemon-reload
sudo systemctl enable --now "$TIMER"
echo "Enabled ONLY isolated five-minute V127 research recorder."
systemctl list-timers --all "$TIMER" --no-pager
echo "Collector remains read-only; no gameplay or public website changes."
