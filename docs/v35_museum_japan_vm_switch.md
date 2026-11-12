# V35 flower/plushie/Japan Xanax prospective pilot — Oct 8, 2026

This supersedes the **Bear Gall recurring test only**. Its previously recorded
evidence stays in the existing database under experiment
`pilot-beargall-v33`. Public V2 behavior never changes.

## Initial recurring group, exact registry champions

| Item | Frozen selected champion | What this release really executes |
| --- | --- | --- |
| `uni:Heather` | Original V18 `dyn3` | Actual frozen V18 single-tick proposal + V2 |
| `can:Wolverine Plushie` | Original V18 `dyn8` | Actual frozen V18 single-tick proposal + V2 |
| `uni:Nessie Plushie` | Recent phase/template selector | **Baseline-only**: specialist not integrated, V2 captured |
| `jap:Xanax` | Japan Xanax specialist | **Baseline-only**: specialist not integrated, V2 captured |

The seven plushie specialists and Japan Xanax remain separate adapter work.
Do not substitute generic V19/V20/V21 for these champions or claim the
baseline-only records test their winning model. The two native V18 predictions
are still **research**, not player-facing travel guidance.

Existing protected environment settings remain unchanged.
No additional secrets or permission changes required.

## Stage A: safety / dry-run

The operator has confirmed V34 installed at `deca908`, with V33 timer
running and V2 unaffected. Pause just the timer before changing on-disk code
so it cannot start a partial-version process:

```bash
cd /opt/torn-fren
sudo systemctl stop torn-fren-shadow-capture.timer
systemctl is-active torn-fren-shadow-capture.service
git status --short
git branch --show-current
```

If the one-shot service is `active` (already finishing a tick), allow it to
finish before touching the checkout. No stop/kill of the poller or website.

```bash
git fetch origin release/v35-flower-plushie-japan-pilot-20261008
git merge-base --is-ancestor HEAD FETCH_HEAD &&
  git branch "backup/pre-v35-$(date +%Y%m%d-%H%M%S)" HEAD &&
  git merge --ff-only FETCH_HEAD
python3 -m unittest discover -s tests -p 'test_v35_museum_japan_private_pilot.py' -v
python3 -m py_compile services/private_v18_champion_worker_v35.py \
  services/private_challenger_adapter_v31.py research/v33_private_shadow_sampler.py
```

Back up just the old unit before replacing it. No systemd environment changes:

```bash
sudo cp -p /etc/systemd/system/torn-fren-shadow-capture.service \
  /etc/systemd/system/torn-fren-shadow-capture.service.pre-v35
sudo install -m 644 deploy/systemd/torn-fren-shadow-capture.service \
  /etc/systemd/system/torn-fren-shadow-capture.service
sudo systemctl daemon-reload
```

### Important: restart the **website only** so the private adapter import is refreshed

```bash
sudo systemctl restart torn-fren-web.service
systemctl is-active torn-fren-web.service
curl -sS -o /dev/null -w 'V2 HTTP %{http_code}\n' \
  'http://127.0.0.1:8000/api/history?country=can&item=Fire%20Hydrant&minutes=60'
systemctl is-active torn-fren-bot.service
systemctl is-active torn-fren-poller.service
```

Do not enable the timer until the private one-shot test succeeds.

## Stage B: one V35 manual four-item capture; approximately 1–3 minutes

```bash
sudo systemctl start torn-fren-shadow-capture.service
sudo systemctl show torn-fren-shadow-capture.service -p Result -p ExecMainStatus
sudo journalctl -u torn-fren-shadow-capture.service -n 22 --no-pager
```

Expect four `RECORDED` rows under **new** experiment
`pilot-museum-japan-v35`. Capture status `RECORDED` proves a private
snapshot was recorded; it does NOT imply the champion generated a departure.
The specialist items must have `challenger_executed=0` for now.

To inspect evidence (no keys printed):

```bash
sudo -u ubuntu python3 - <<'PY'
import sqlite3
p='/var/lib/torn-fren-shadow/capture.db'
with sqlite3.connect('file:'+p+'?mode=ro',uri=True) as con:
 print('V35 capture outcomes:')
 print(con.execute('''
   SELECT item_key,status,COUNT(*) FROM shadow_capture_attempts
   WHERE experiment_id='pilot-museum-japan-v35'
   GROUP BY item_key,status ORDER BY item_key
 ''').fetchall())
 print('V35 native vs baseline-only:')
 print(con.execute('''
   SELECT item_key,candidate_model_family,candidate_config,
          challenger_status,challenger_executed,
          v2_departure,challenger_departure
   FROM shadow_decisions
   WHERE experiment_id='pilot-museum-japan-v35'
   ORDER BY item_key
 ''').fetchall())
PY
```

### Stage C: enable the already-installed timer only after verifying Stage B

```bash
sudo systemctl start torn-fren-shadow-capture.timer
systemctl is-active torn-fren-shadow-capture.timer
systemctl list-timers --all torn-fren-shadow-capture.timer
```

The existing timer remains installed and enabled from V33; `start`
reactivates the paused timer. It collects at :01/:06/:11/... (UTC), does not
backfill and never changes public V2. The new one-shot service has a 275s
timeout for four serial predictions; if it exceeds that bound, the next timer
tick may be skipped. Count such misses in V34 forward reporting. No other
production services are stopped.

### Rollback for unexpected web errors

If V2/public endpoints become unhealthy, first restore previous checkout
branch to the backed-up V34 commit using the earlier saved backup branch,
restore the old systemd service unit and restart **only** the web service.
Preserve collector and evidence SQLite databases. This pilot is an optional
research diagnostic; disable the timer rather than risking the website.

## Scoring

Run V34 with `--experiment pilot-museum-japan-v35`, `--item` for each
selected item, and a new actual `--freeze-epoch` equal to the first V35
capture time. Determine `--scheduled-from-epoch` from the first timer
firing AFTER switching (must be a :01/:06/... minute). The old Bear Gall
timestamps are not applicable.

Use 8h native planning for the two original V18 champions and do not
confuse that with Japan Xanax's separate timing evaluation. The current
V34 scorer assumes one common policy maximum per invocation; **separate
specialist pilot scoring and model-specific horizon settings** before
reporting final comparable rates. Independent window certification remains
blocked. No public promotion.
