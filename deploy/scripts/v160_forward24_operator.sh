#!/usr/bin/env bash
# Opt-in V160 prospective 24-item independent and paired V151 private shadow.
# status|smoke|record|report|enable|disable
set -euo pipefail
export SYSTEMD_PAGER=cat
ACTION="$(printf '%s' "${1:-status}" | tr -d '\015')"
case "$ACTION" in status|smoke|record|report|enable|disable) ;;
  *) echo 'Use status|smoke|record|report|enable|disable'; exit 2 ;;
esac
[[ "$(id -un)" == ubuntu ]] || { echo "STOP run as ubuntu"; exit 1; }
UNIT=torn-fren-v160-forward24
TIMER="${UNIT}.timer"
SERVICE="${UNIT}.service"
WORK=/home/ubuntu/torn-fren-v38-probe
STAGE=/home/ubuntu/torn-fren-private-models/v160_stage/pinned
PRIVATE=/var/lib/torn-fren-v38
COLLECTOR=/opt/torn-fren/data/stock_history.db
PIN=510ea2fd2d6cfe3f124493a786cd1ef338c5995b
PY="$WORK/.venv/bin/python"

if [[ "$ACTION" == status ]]; then
  echo "===== V160 PRIVATE PROSPECTIVE STATUS ====="
  systemctl is-enabled "$TIMER" 2>/dev/null || true
  systemctl is-active "$TIMER" 2>/dev/null || true
  systemctl list-timers --all "$TIMER" --no-pager || true
  test ! -f "$PRIVATE/v160_v151_prospective24.db" ||
    ls -lh "$PRIVATE/v160_v151_prospective24.db"
  echo "Collector and original/experimental websites not modified."
  exit 0
fi

if [[ "$ACTION" == disable ]]; then
  sudo systemctl disable --now "$TIMER" || true
  echo "Disabled ONLY ${TIMER}"
  exit 0
fi

test -r "$COLLECTOR" || { echo "STOP approved collector unreadable"; exit 1; }
test -d "$PRIVATE" || { echo "STOP private sidecar dir missing"; exit 1; }
test -x "$PY" || { echo "STOP Python venv unavailable"; exit 1; }
test -d "$WORK/.git" || { echo "STOP research checkout unavailable"; exit 1; }
test ! -L "$STAGE" || { echo "STOP isolated research stage symlink"; exit 1; }
cd "$WORK"
git fetch -q origin research/v38-full-roster-live-prep-20261009
git cat-file -e "${PIN}^{commit}"

mkdir -p "$STAGE/research/plushie_champions"
for name in \
  v34_prospective_ops_audit \
  v38_prediction_store \
  v57_exception_fingerprint \
  v60_private_snapshot_probe \
  v76_forward_research_report \
  v88_poll_state_forward_report \
  v102_restock_departure_bridge \
  v107_explicit_restock_cycle_baseline \
  v109_raw_restock_transition_event_audit \
  v123_empirical_phase_survival_challenger \
  v125_earliest_credible_shadow \
  v128_full24_earliest_shadow \
  v145_provider_continuous_phases \
  v151_stable_earliest_departure \
  v160_prospective_v151_shadow \
  v161_prospective_v151_forward_report
do
  test ! -L "$STAGE/research/$name.py" ||
    { echo "STOP stage module symlink: $name"; exit 1; }
  git show "${PIN}:research/${name}.py" > "$STAGE/research/$name.py"
  "$PY" -m py_compile "$STAGE/research/$name.py"
done
for name in __init__ common; do
  git show "${PIN}:research/plushie_champions/${name}.py" \
    > "$STAGE/research/plushie_champions/$name.py"
done
git show "${PIN}:research/v38_roster.json" > "$STAGE/research/v38_roster.json"
git show "${PIN}:deploy/scripts/v160_forward_shadow_launcher.py" \
  > "$STAGE/v160_forward_shadow_launcher.py"

export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
case "$ACTION" in
  smoke|enable)
    echo '===== V160 24-ITEM NO-WRITE SMOKE ====='
    nice -n 19 timeout 150s "$PY" "$STAGE/v160_forward_shadow_launcher.py" --preview
    if [[ "$ACTION" == smoke ]]; then
      echo "SMOKE PASS; V160 timer is NOT enabled or installed"
      exit 0
    fi ;;
  record)
    echo '===== EXPLICIT V160 PRIVATE ONE-TIME RECORD ====='
    nice -n 19 timeout 150s "$PY" "$STAGE/v160_forward_shadow_launcher.py" --record
    exit 0 ;;
  report)
    echo '===== V161 GENUINE PROSPECTIVE ARRIVAL REPORT ====='
    nice -n 19 timeout 75s "$PY" "$STAGE/v160_forward_shadow_launcher.py" --report
    exit 0 ;;
esac

# Only explicit enable after successful smoke can reach installation.
for unit in "$SERVICE" "$TIMER"; do
  target="/etc/systemd/system/$unit"
  tmp="/tmp/${unit}.v160-pinned"
  git show "${PIN}:deploy/systemd/${unit}" > "$tmp"
  if sudo test -e "$target" && ! sudo cmp -s "$tmp" "$target"; then
    echo "STOP existing unit differs; refusing to replace $unit"
    exit 1
  fi
done
for unit in "$SERVICE" "$TIMER"; do
  sudo install -o root -g root -m 0644 "/tmp/${unit}.v160-pinned" \
    "/etc/systemd/system/$unit"
done
sudo systemctl daemon-reload
sudo systemctl enable --now "$TIMER"
echo "Only new V160 private timer enabled. V75/V128/V2/experimental site untouched."
systemctl list-timers --all "$TIMER" --no-pager
