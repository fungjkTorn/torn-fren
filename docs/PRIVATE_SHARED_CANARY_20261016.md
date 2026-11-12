# Private shared recommendation canary

Status: implementation tested and committed; owner-side preflight and live start pending.

Tested implementation pin: `00bbfa9355bcb76954feefae2b6d8c930c68426a`. [CI run 38942179526](https://github.com/fungjkTorn/torn-fren/actions/runs/38942179526) passed both causal/contract and browser jobs. V35, V38 and profitability compatibility workflows also passed. These checks establish software behavior, not live prediction accuracy.

This trial serves a separate website on **127.0.0.1:8770**. It reads the existing graph API on localhost:8000 and the collector SQLite database in read-only mode. It does not install services, replace deployed files, change collector permissions, or alter ports 8000, 8001 or 8765. Stop the foreground process with Ctrl+C to stop the trial.

The explicit profile contains 24 verified items: 14 flower/plushie candidates enabled, seven weaker plushies and three Xanax disabled. Four original roster identities remain unresolved. Enabled means selected for this research preview, not release-qualified accuracy. True depletion remains exactly zero; the arrival target remains 30 units. The 30-second publication tolerance applies only to original leave-now plans. Historical five-minute replay results do not establish live accuracy at this producer's 20-second cadence.

## Owner preparation

Use the existing owner SSH session. Set `CANARY_PIN` to the exact tested implementation SHA supplied with the rollout, then run the following on the VM. Use a fresh checkout; do not pull this branch over the deployed app.

```bash
set -e
CANARY_PIN=00bbfa9355bcb76954feefae2b6d8c930c68426a
: "${CANARY_PIN:?Set the tested 40-character implementation SHA first}"
CANARY_CODE="$HOME/torn-fren-shared-canary-${CANARY_PIN:0:12}"
CANARY_STATE="$HOME/torn-fren-shared-canary-state-${CANARY_PIN:0:12}"
git clone --single-branch --branch research/v38-full-roster-live-prep-20261009 https://github.com/fungjkTorn/torn-fren.git "$CANARY_CODE"
cd "$CANARY_CODE"
git checkout --detach "$CANARY_PIN"
python3.12 -m venv .venv
.venv/bin/python -m pip install numpy==1.26.4
.venv/bin/python -m deploy.scripts.shared_canary \
  --source /opt/torn-fren/data/stock_history.db \
  --state "$CANARY_STATE" --model-sha "$CANARY_PIN" \
  --port 8770 --preflight-only
```

Preflight requires a clean pinned checkout, unused port, recognized experimental HTML, a separate state directory, a successful build within 20 seconds, and a fresh shared snapshot. It prints `PRIVATE_CANARY_READY`, source SHA, item count, source age and build duration. It may write only its separate state files. If the owner cannot read the database or upstream source differs, stop and review the error; do not broaden the runner's permissions or replace the source HTML guard.

After a successful preflight, start the foreground canary in that same shell:

```bash
.venv/bin/python -m deploy.scripts.shared_canary \
  --source /opt/torn-fren/data/stock_history.db \
  --state "$CANARY_STATE" --model-sha "$CANARY_PIN" --port 8770
```

The publisher uses the pinned checkout explicitly, avoiding the VM's older default research import path. Each subprocess has a 25-second timeout. The producer attempts a build every 20 seconds; this cadence is a target, not a measured live performance guarantee. Requests only read the completed atomic snapshot. Stale, missing, or mismatched data clears the shared recommendation rather than selecting an incumbent.

## Connect and review

In a separate local terminal, use the same owner SSH key and VM address as the existing tunnel, forwarding **127.0.0.1:8770 to 127.0.0.1:8770**, with `ExitOnForwardFailure=yes`. Keep that terminal and the foreground server open.

Visit:

- `http://127.0.0.1:8770/health` — fresh source and exact pin.
- `http://127.0.0.1:8770/` — existing V2 graph plus shared recommendation panel.
- `http://127.0.0.1:8770/experimental` — recovered table/graph with shared recommendations.
- `http://127.0.0.1:8770/travel-decisions` — the same shared snapshot and selected policy.

Review live build duration, source age, expiry behavior, agreement between the three views, and actual availability at the suggested arrival before promoting any policy. Existing V2 predictions remain visible as legacy graph information; the new panel identifies the shared departure estimate. No verified live success percentage is supplied by this trial.

## Rollback

Ctrl+C the foreground canary and close its 8770 tunnel. Existing production services continue independently. Leave the isolated checkout and state for review; no production rollback command is needed.
