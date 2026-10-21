# V38 research integration checkpoint — October 9, 2026

**Branch:** `research/v38-full-roster-live-prep-20261009`. No commit here was
merged to `main` or deployed to the Oracle production checkout.

## Actual implementation, not promotion claims

- **16 of 22** exact source-pinned candidates remain executable through the
  original isolated V18/V19/V20/Nessie/Camel research wrappers.
- **Red Fox** now has a separate original k18 / global regime 0.5 candidate
  adapter (`research.v38_red_fox_single_tick`). It reads all ten cross-plushie
  histories and **is not scheduled** until a VM cold-run CPU/RSS benchmark,
  independent as-of parity and stock-gap checks pass.
- **Lion, Panda, Monkey, Chamois, Japan Xanax** remain without deployable
  genuine specialists. Never substitute generic V2 or "best current expert"
  and label it their winning algorithm.
- `research/v38_incremental_observer.py` observes collector row IDs in capped
  chunks using `mode=ro`. A partial bootstrap is explicitly not ready.
  The separate feature-cache API keys by item, model config, schema revision,
  last material-change row ID, collection gap revision and clock slot.
  **The 16 original model engines are not yet converted to consume cached
  feature arrays**. This is a safe underlying primitive, not a claim that
  repeated historical model preparation has been eliminated.
- `research/v38_prediction_store.py`: small, separate SQLite WAL sidecar,
  one latest row per item; 5-minute expiry for newly computed proposals;
  missing/expired/failing models demand V2 fallback, no invented accuracy.
- `research/v38_catalog_seed.py`: explicit 236-item registry seeded as
  fallback/watch/provisional states. Only 16 are marked benchmark-gated
  adapters, *not* approved for public beta.
- `research/v38_adaptive_policy.py`: actionability stays at a five-minute
  cadence; cold non-actionable models can defer up to 30 minutes (one hour
  only with observed day-scale intervals). Normal identical-quantity poll
  snapshots do not invalidate the historical cache; material quantity changes
  and gap revisions do.
- `research/v38_budgeted_runner.py`: opt-in **serial** work, at most four
  source-pinned workers by default, 20 seconds each and a global 85-second
  budget. Active requested items are prioritized; unfunded work remains
  deferred. The scheduler does not meet five-minute cadence for *every* item
  unless demonstrated by measurements.
- `/api/research/v38/predictions`: default-off on the **research branch**.
  Requires `TORN_FREN_V38_EXPERIMENTAL_API=1` and
  `TORN_FREN_V38_SNAPSHOT_DB`. Reads the sidecar in read-only mode and never
  performs champion inference. This is backend only, no finished UI.
- Existing V37 production V2, website, bot, poller and four-item research
  timer have not been modified or restarted.

## Read-only diagnostics — do this BEFORE considering deployment

From Windows PowerShell:

```powershell
ssh -i "C:\Users\fungb\Desktop\.ssh\torn-fren.key" ubuntu@150.136.108.146
```

On the Oracle VM:

```bash
cd /opt/torn-fren
printf '\nBRANCH: '; git branch --show-current
printf '\nHEAD: '; git rev-parse --short HEAD
git status --short
nproc
lscpu | grep -E 'CPU\(s\)|Model name|Thread|Core'
free -h
uptime
vmstat 1 5
df -h / /opt/torn-fren
ps -eo pid,comm,%cpu,%mem,rss --sort=-%cpu | head -20
command -v nvidia-smi >/dev/null && nvidia-smi || echo 'No NVIDIA GPU reported'
systemctl is-active torn-fren-web.service torn-fren-bot.service torn-fren-poller.service torn-fren-shadow-capture.timer
systemctl show torn-fren-shadow-capture.service -p CPUQuotaPerSecUSec -p MemoryMax -p TimeoutStartUSec
du -h /opt/torn-fren/data/stock_history.db
for i in $(seq 1 20); do curl -sS -o /dev/null --max-time 15 -w '%{http_code} %{time_total}\n' http://127.0.0.1:8000/api/catalog; done
```

Note the HTTP code and 20 elapsed times. Repeat after any isolated test to
detect site latency regressions. No GPU purchase is indicated without evidence.

## Separate, non-production worktree (no production checkout switch)

Run **only after** checking hardware/resource headroom, and leave the existing
systemd research timer active:

```bash
cd /opt/torn-fren
git fetch origin research/v38-full-roster-live-prep-20261009
git worktree add --detach /home/ubuntu/torn-fren-v38 FETCH_HEAD
cd /home/ubuntu/torn-fren-v38
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install -r research/plushie_champions/requirements-research.txt
# Plan/status only: no collector or sidecar writes, no execution
.venv/bin/python -m research.v38_catalog_seed --sidecar /home/ubuntu/torn-fren-v38-research.db
.venv/bin/python -m research.v38_budgeted_runner --sidecar /home/ubuntu/torn-fren-v38-research.db
```

After CPU/RAM/website measurements prove headroom and with your **explicit**
permission, an isolated small smoke run could be:

```bash
cd /home/ubuntu/torn-fren-v38
nice -n 15 timeout 110s .venv/bin/python -m research.v38_readonly_resource_probe --db /opt/torn-fren/data/stock_history.db --timeout 20 --budget 100
```

This probe neither alters the collector nor starts a service. The V38
scheduler's `--execute` and catalogue seeder's `--execute` are separately
opt-in; do **not** add a systemd timer, public env flags or modify
`profitability-v1` until the canary is reviewed.

## Beta acceptance gates for October 14

- Full compatibility CI green on one stable branch head; source-pinned model
  parity tested for every specialist offered to users.
- Resource measurements: peak RSS, CPU, worker wall times and 20+ baseline
  catalog requests, with the same measurements during an isolated workload.
- No observed poller gaps, missed V37 timer work, bot outages, or repeated web
  p95 >1 second caused by V38.
- Fast snapshot reads with explicit provenance, expiry and visible
  experimental wording, and V2 fallback when stale/not validated.
- Record forward evidence by **independent resolved stock windows**, plus
  missed/deferred/late recommendations; never infer live accuracy from
  repeatedly scored five-minute ticks or development holdout percentages.
