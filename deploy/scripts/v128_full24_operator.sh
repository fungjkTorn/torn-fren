#!/usr/bin/env bash
# V128 exact 24-item private-only research operator. No VM changes on status.
# smoke stages pinned sources and runs one read-only preview; enable is explicit.
set -euo pipefail
export SYSTEMD_PAGER=cat

ACTION="$(printf '%s' "${1:-status}" | tr -d '\015')"
case "$ACTION" in
  status|smoke|enable|disable) ;;
  *) echo "Usage: status|smoke|enable|disable"; exit 2 ;;
esac
[[ "$(id -un)" == "ubuntu" ]] || {
  echo "STOP: run as ubuntu"; exit 1;
}

UNIT=torn-fren-v128-full24-shadow
SERVICE="$UNIT.service"
TIMER="$UNIT.timer"
WORK=/home/ubuntu/torn-fren-v38-probe
STAGE=/home/ubuntu/torn-fren-private-models/v128_stage/pinned
ROOT=/var/lib/torn-fren-v38
BUNDLE=3c73f931c6e9e7c21f46d813a0fc98550416f0ae
SOURCE=/opt/torn-fren/data/stock_history.db
OPERATOR_DIR=/etc/systemd/system

if [[ "$ACTION" == status ]]; then
  echo "===== OPTIONAL V128 24-ITEM RESEARCH STATUS ====="
  systemctl is-enabled "$TIMER" 2>/dev/null || true
  systemctl is-active "$TIMER" 2>/dev/null || true
  systemctl list-timers --all "$TIMER" --no-pager || true
  echo "===== EXISTING V38 RESEARCH ====="
  systemctl is-active torn-fren-v38-private-shadow.timer 2>/dev/null || true
  echo "===== 24-ITEM SIDECAR ====="
  if [[ -f "$ROOT/v128_earliest24_shadow.db" ]]; then
    ls -lh "$ROOT/v128_earliest24_shadow.db"
  else
    echo "Not created: prospective V128 24-item capture not yet enabled"
  fi
  exit 0
fi

if [[ "$ACTION" == disable ]]; then
  sudo systemctl disable --now "$TIMER" || true
  echo "Only V128 research timer disabled. Existing V38/V75/V82/V85 unchanged."
  exit 0
fi

cd "$WORK"
test -r "$SOURCE" || { echo "STOP: collector source unreadable"; exit 1; }
test -d "$ROOT" || { echo "STOP: private sidecar directory unavailable"; exit 1; }
test -x .venv/bin/python || { echo "STOP: V38 Python venv unavailable"; exit 1; }
if systemctl is-active --quiet torn-fren-v127-earliest-shadow.timer; then
  echo "STOP: V127 two-item timer running, do not duplicate it."; exit 1
fi

git fetch origin research/v38-full-roster-live-prep-20261009
git cat-file -e "${BUNDLE}^{commit}"

mkdir -p "$STAGE/research/plushie_champions"
for name in \
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
  v125_earliest_credible_shadow \
  v128_full24_earliest_shadow
do
  git show "${BUNDLE}:research/${name}.py" \
    > "$STAGE/research/${name}.py"
  python3 -m py_compile "$STAGE/research/${name}.py"
done

for name in __init__ common
do
  git show "${BUNDLE}:research/plushie_champions/${name}.py" \
    > "$STAGE/research/plushie_champions/${name}.py"
done
git show "${BUNDLE}:research/v38_roster.json" \
  > "$STAGE/research/v38_roster.json"
git show "${BUNDLE}:deploy/scripts/v128_shadow_launcher.py" \
  > "$STAGE/v128_shadow_launcher.py"

echo "===== PREVIEW OF 24 MODEL RECOMMENDATIONS (NO DATABASE WRITES) ====="
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 \
  OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  nice -n 15 timeout 130s \
  .venv/bin/python "$STAGE/v128_shadow_launcher.py" --preview

echo "Pinned full-24 smoke preview succeeded. No timer changed."
if [[ "$ACTION" == smoke ]]; then
  exit 0
fi

# Explicit enable-only installation, never modify a preexisting different unit.
for name in "$SERVICE" "$TIMER"; do
  git show "${BUNDLE}:deploy/systemd/$name" > "/tmp/$name.v128-checked"
  if sudo test -e "$OPERATOR_DIR/$name" &&
     ! sudo cmp -s "/tmp/$name.v128-checked" "$OPERATOR_DIR/$name"; then
    echo "STOP: existing $name differs, refusing to overwrite"; exit 1
  fi
done
for name in "$SERVICE" "$TIMER"; do
  sudo install -o root -g root -m 0644 \
    "/tmp/$name.v128-checked" "$OPERATOR_DIR/$name"
done
sudo systemctl daemon-reload
sudo systemctl enable --now "$TIMER"
echo "Enabled only independent V128 24-item private research timer."
systemctl list-timers --all "$TIMER" --no-pager
echo "Website, production stock collector and existing champions unchanged."
