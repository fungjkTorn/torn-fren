#!/usr/bin/env bash
# V160 private beta viewer only. Does NOT edit /opt/torn-fren, V2, experimental,
# the collector, existing timers, or the research forecast sidecar.
set -euo pipefail
ACTION="$(printf '%s' "$@" | tr -d '\015')"
[[ -n "$ACTION" ]] || ACTION=status
case "$ACTION" in install|status|stop) ;; *) echo "Use install|status|stop"; exit 2;; esac
[[ "$(id -un)" == ubuntu ]] || { echo "STOP run as ubuntu"; exit 1; }
UNIT=torn-fren-v160-beta-board.service
WORK=/home/ubuntu/torn-fren-v38-probe
PRIVATE=/home/ubuntu/torn-fren-private-models
CODE="$PRIVATE/v160_beta_board.py"
LEDGER=/var/lib/torn-fren-v38/v160_v151_prospective24.db
ROSTER="$PRIVATE/v160_stage/pinned/research/v38_roster.json"
BRANCH=research/v38-full-roster-live-prep-20261009
# Immutable source bundle containing the beta code AND dedicated systemd unit.
PIN=2abfecb932cf5551a49039f865f49c8bf5718247

if [[ "$ACTION" == status ]]; then
  echo "===== PRIVATE BETA SERVICE STATUS ====="
  systemctl is-enabled "$UNIT" 2>/dev/null || true
  systemctl is-active "$UNIT" 2>/dev/null || true
  systemctl show "$UNIT" -p ActiveState -p SubState -p ExecMainStatus --no-pager || true
  echo "Expected private URL: http://127.0.0.1:8765/"
  # 503 may mean temporarily stale research data, not that the web app died.
  curl -s -o /dev/null -w "Private API HTTP: %{http_code}\n" --max-time 3 \
    http://127.0.0.1:8765/api/live || true
  exit 0
fi
if [[ "$ACTION" == stop ]]; then
  sudo systemctl disable --now "$UNIT"
  echo "Stopped ONLY the private beta board. V160 recorder continues unchanged."
  exit 0
fi
[[ -r "$LEDGER" && -r "$ROSTER" ]] || {
  echo "STOP V160 private ledger/roster missing; do not invent departures"; exit 1;
}
[[ -d "$PRIVATE" && ! -L "$PRIVATE" && ! -L "$CODE" ]] || {
  echo "STOP unsafe private beta stage"; exit 1;
}
[[ "$(git -C "$WORK" rev-parse --show-toplevel 2>/dev/null || true)" == "$WORK" ]] || {
  echo "STOP research worktree missing"; exit 1;
}
cd "$WORK"
git fetch -q origin "$BRANCH"
git cat-file -e "$PIN^{commit}"
tmp="$(mktemp "$PRIVATE/.v160-beta.XXXXXXXX")"
unit_tmp="$(mktemp /tmp/.v160-beta-unit.XXXXXXXX)"
trap 'rm -f "$tmp" "$unit_tmp"' EXIT
git show "$PIN:deploy/scripts/v160_private_beta_board.py" > "$tmp"
git show "$PIN:deploy/systemd/$UNIT" > "$unit_tmp"
python3 -m py_compile "$tmp" || {
  echo "STOP private beta Python syntax invalid"; exit 1;
}
# Preview the REAL complete last batch before installing any new unit.
python3 -I - "$tmp" <<'PY'
import json,runpy,sys
m=runpy.run_path(sys.argv[1])
r=m["snapshot"]()
print(json.dumps({
    "preview":"V160_BETA_READ_ONLY",
    "issued_epoch":r["issued_epoch"],
    "recorded_items":r["recorded_items"],
    "research_data_fresh":r["healthy"],
    "proposals":sum(x["available"] for x in r["items"]),
    "collector_written":False,
    "websites_modified":False
},sort_keys=True))
if not r["healthy"] or r["recorded_items"]!=24:
    raise SystemExit("STOP stale or incomplete private research snapshot")
PY
target="/etc/systemd/system/$UNIT"
if sudo test -e "$target" && ! sudo cmp -s "$unit_tmp" "$target"; then
  echo "STOP existing dedicated beta unit differs; won't overwrite it"
  exit 1
fi
# Never change an already running executable behind systemd's back.
if systemctl is-active --quiet "$UNIT"; then
  if [[ -f "$CODE" ]] && cmp -s "$CODE" "$tmp"; then
    echo "Already running identical private beta. No replacement needed."
    systemctl is-active "$UNIT"
    exit 0
  fi
  echo "STOP beta service already active on different source, review upgrade first"
  exit 1
fi
install -m 0700 "$tmp" "$CODE"
sudo install -o root -g root -m 0644 "$unit_tmp" "$target"
sudo systemctl daemon-reload
sudo systemctl enable --now "$UNIT"
echo "Private beta enabled. Bound ONLY to VM 127.0.0.1:8765."
echo "V160 collector/recorder, V75/V128 timers and both websites unchanged."
systemctl is-active "$UNIT"
