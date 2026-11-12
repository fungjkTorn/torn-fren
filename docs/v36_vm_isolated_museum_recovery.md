# V36 emergency private-shadow performance hardening — Oct 8, 2026

Production evidence motivating the release (from the live VM logs):
- Public web immediately after restart returned HTTP 000 before Uvicorn bound;
  subsequent `/api/catalog` returned HTTP 200; bot and poller stayed active.
- V35 four-item research sampler ran ~3.5 minutes; Heather responded 200
  but Wolverine/Nessie/Japan timed out, so timer was paused by operator.
- V35's private HTTP handler **synchronously recalculated V2** for each
  requested item. It is unsafe to send all four every five minutes on the VM.

## V36: no public routing changes; no restart of website/bot/poller

One item per timer firing, round-robin:
1. UK Heather, **true frozen V18 dyn3** child only
2. Canada Wolverine Plushie, **true frozen V18 dyn8** child only
3. UK Nessie Plushie, **V2 baseline only**, specialist not integrated
4. Japan Xanax, **V2 baseline only**, specialist not integrated

The order above is the rotation set, not necessarily the item for the next
clock tick; the chosen item is deterministic via Unix five-minute slot modulo
four. Each item gets one opportunity every **20 min**, not every five minutes.
A frozen V18 worker has a hard timeout of 38 seconds. Its child reads the
stock collector SQLite via read-only URI. The public V2 reference is requested
from existing `/api/history` with a strict 3-second timeout: the API's
nonblocking prediction cache may respond `warming`, which is saved honestly,
not treated as a model success. No token is required or exposed.

Systemd's research-only sandbox enforces `Nice=15`, `CPUQuota=50%`,
`MemoryMax=512M`, `TimeoutStartSec=75`. Its environment does NOT include
the private shadow auth token. The existing private V35 endpoint remains
installed but is NOT used by the timer. Public V2 routing is unchanged.

## Safe operator rollout — stop before each checkpoint on failures

**Timer remains stopped** from the prior failed V35 run. Do not re-enable it
until all manual validation stages pass.

1. Confirm `curl -f -m 10 http://127.0.0.1:8000/api/catalog` returns 200,
   `systemctl is-active torn-fren-web.service`, bot, poller all active.

2. Fast-forward clean deployed `profitability-v1` branch from `e9ac999`:

```bash
cd /opt/torn-fren
test "$(git branch --show-current)" = "profitability-v1" || exit 2
test -z "$(git status --porcelain)" || exit 2
git fetch origin release/v36-isolated-rotating-museum-pilot-20261008
git merge-base --is-ancestor HEAD FETCH_HEAD || exit 2
git branch "backup/pre-v36-$(date +%Y%m%d-%H%M%S)" HEAD
git merge --ff-only FETCH_HEAD
python3 -m unittest discover -s tests -p 'test_v36_isolated_museum_sampler.py' -v
python3 -m py_compile research/v36_isolated_museum_sampler.py
```

No production service restart is needed. The updated V36 sampler starts only
when explicitly invoked; existing V35 code remains dormant.

3. **Manual isolated smoke on one frozen champion**, without systemd timer or
   private HTTP endpoint. The experiment ID distinguishes it from scheduled
   capture. Do NOT paste the source env file or token.

```bash
cd /opt/torn-fren
sudo -u ubuntu nice -n 15 timeout 55s python3 -m \
 research.v36_isolated_museum_sampler \
 --db /opt/torn-fren/data/stock_history.db \
 --evidence-db /var/lib/torn-fren-shadow/capture.db \
 --experiment pilot-v36-manual-heather \
 --item 'uni:Heather'
```

Inspect `native_status` and `champion_executed`, not only
`status=RECORDED`. For Heather, require `champion_executed=true`;
if it returns `NATIVE_WORKER_TIMEOUT`, do NOT start the timer. V2 status can
be `warming` and is not an error if the native result is correct. If Heather
passes, optionally repeat with `--item 'can:Wolverine Plushie'` and a
new experiment name `pilot-v36-manual-wolverine`.

4. Before changing unit, back up the V35 unit and evidence ledger while
   sampler is stopped (do not overwrite any previous backup):

```bash
sudo cp -p /etc/systemd/system/torn-fren-shadow-capture.service \
 /etc/systemd/system/torn-fren-shadow-capture.service.pre-v36
sudo cp -p /var/lib/torn-fren-shadow/capture.db \
 /var/lib/torn-fren-shadow/capture.db.pre-v36
sudo install -m 644 deploy/systemd/torn-fren-shadow-capture.service \
 /etc/systemd/system/torn-fren-shadow-capture.service
sudo systemctl daemon-reload
```

5. With timer still OFF, launch one unit run:

```bash
sudo systemctl start torn-fren-shadow-capture.service
sudo systemctl show torn-fren-shadow-capture.service -p Result -p ExecMainStatus
sudo journalctl -u torn-fren-shadow-capture.service -n 12 --no-pager
```

The chosen item varies by clock slot; expect exactly ONE new line for V36.
If the item is a specialist, expect `champion_executed=false` and
`native_status=\\"SPECIALIST_NOT_INTEGRATED\\"`. If it is Heather/Wolverine,
expect `true` only if original V18 created a valid departure.
Check the public website and both production services again.

6. **Only after manual V36 checks pass**, operator may resume timer:

```bash
sudo systemctl start torn-fren-shadow-capture.timer
systemctl list-timers --all torn-fren-shadow-capture.timer
```

The timer was previously enabled under V33; restarting it does not modify
the five-minute schedule. Do not allow concurrent old and new services.

### Stop / rollback

```bash
sudo systemctl stop torn-fren-shadow-capture.timer
sudo cp -p /etc/systemd/system/torn-fren-shadow-capture.service.pre-v36 \
 /etc/systemd/system/torn-fren-shadow-capture.service
sudo systemctl daemon-reload
```

Leave timer STOPPED if V35 fallback proves too expensive. No web restart and
no rollback of the running V2 public service is necessary. Preserve all SQLite
evidence; experiment IDs segregate the old Bear Gall and failed V35 trials.

## Honest forward scorekeeping

V34 read-only scorer now accepts `--schedule-stride-seconds 1200` for the
rotating pilot instead of incorrectly charging each item for the other
three items' scheduled slots. Do not score specialist champions as present.
Use `--experiment pilot-museum-japan-v36` with the actual first V36
`--freeze-epoch` and first scheduled tick for EACH requested item. Before
the 8h planning horizon plus flight and observation windows mature, record
pending predictions, not 0%/100% win rates. All items remain blocked from
promotion pending independent forward stock-window certification.
