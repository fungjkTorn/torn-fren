# V34 VM prospective operational scoring (separate from public forecasts)

Status: read-only research preview, NOT live travel guidance, not release approval.
Based on running V33 capture commit `9eef543`. No website, Discord, poller,
arbitrage, private token, systemd timer, or stock collector changes are needed.

## Real confirmed pilot anchor (do not backdate)
- Initial manually captured prospective Bear Gall tick: `1791499203` (Oct 8, 22:40:03 UTC)
- User-verified next enabled systemd timer fire: `1791499560` (Oct 8, 22:46:00 UTC)
- Frozen model: `can:Bear Gall`, V21 `dyn12`, 12-hour policy horizon.
- Experiment ID: `pilot-beargall-v33`
- These times originate from the original user-supplied live VM logs; no
  retrospective sessions can be added before the first prospective snapshot.

## Step A: verify timer after at least one scheduled tick

```bash
systemctl is-active torn-fren-shadow-capture.timer
systemctl list-timers --all torn-fren-shadow-capture.timer
sudo journalctl -u torn-fren-shadow-capture.service -n 20 --no-pager
sudo -u ubuntu python3 - <<'PY'
import sqlite3
p='/var/lib/torn-fren-shadow/capture.db'
with sqlite3.connect('file:'+p+'?mode=ro',uri=True) as db:
    print('Attempts', db.execute(
      'SELECT count(*) FROM shadow_capture_attempts').fetchone()[0])
    print('Statuses', db.execute(
      'SELECT status,count(*) FROM shadow_capture_attempts GROUP BY status').fetchall())
    print('Accepted decisions', db.execute(
      'SELECT count(*) FROM shadow_decisions').fetchone()[0])
PY
```

The timer must show successive `RECORDED` results, or an explicitly recorded
failure; otherwise stop further deployment and diagnose. Do not confuse
`systemctl active` alone with successful periodic sampling.

## Step B: bring in the isolated scorer; NO restart

```bash
cd /opt/torn-fren
if [ "$(git branch --show-current)" != "profitability-v1" ] || \
   [ -n "$(git status --porcelain)" ]; then
    echo 'STOP: unexpected VM branch or local edits'
else
    git fetch origin research/v34-vm-prospective-audit-20261008 &&
    git merge-base --is-ancestor HEAD FETCH_HEAD &&
    git branch "backup/pre-audit-$(date +%Y%m%d-%H%M%S)" HEAD &&
    git merge --ff-only FETCH_HEAD &&
    python3 -m unittest discover -s tests -p 'test_v34_prospective_ops_audit.py' -v
fi
```

The scored outcomes require the frozen waiting horizon + Canada flight (27m)
+10sec grace +180sec bracketing observations to mature. Expect initial
`pending_attempts > 0`, `matured_attempts_or_missing_ticks = 0`, and
`conservative_success_lower_bound = null`. That means NOT YET MEASURABLE,
not zero success.

## Step C: inspect research results without writing files

```bash
cd /opt/torn-fren
python3 -m research.v34_prospective_ops_audit \
  --evidence-db /var/lib/torn-fren-shadow/capture.db \
  --stock-db /opt/torn-fren/data/stock_history.db \
  --experiment pilot-beargall-v33 \
  --freeze-epoch 1791499203 \
  --scheduled-from-epoch 1791499560 \
  --max-wait-seconds 43200 \
  --item 'can:Bear Gall'
```

Start interpreting completed arrivals after the first full 12h waiting/flight
horizon matures. Confirm the duration and independent-stock event counts
before any public switch.

This command does not update the shadow SQLite or stock collector DB.
It prints a JSON operational summary including captured/failed/missing slots,
V21 and V2 outcomes, data gaps and incomplete windows. It does not capture
additional predictions and does not need scheduling.

### What the reported metrics mean

- `conservative_success_lower_bound`: confirmed successful arrivals divided
  by all matured sampled/expected opportunities, including failed/missing
  scheduled slots and unscorable outcomes as **no confirmed success**. It's a
  conservative operational floor, not a calibrated per-trip probability.
- `recorded_arrival_rate`: conditional rate among *verified* actionable
  arrival recommendations, excluding no recommendation and ambiguous outcomes.
  It should **never** be cited alone as production success.
- `pending_attempts`: not evaluated until a complete 12-hour policy horizon
  plus travel time and stock observation grace has matured.
- `missing_timer_ticks`: expected schedule slots absent from attempted logs.
  Keep these in the operational denominator.
- `observed_completed_high_stock_segments_diagnostic_only`: not a certified
  sample of independent restock windows.
- `independent_window_certified=false` and `promotions_approved=0`
  regardless of interim positive results.

## Stop the sampler if unusual load develops

```bash
sudo systemctl disable --now torn-fren-shadow-capture.timer
```

This stops only the new private capture timer, leaving V2 web/bot/poller
running. Do not print or upload private token contents. Never merge generic
research PRs into the main VM branch directly or start new auto-travel.
