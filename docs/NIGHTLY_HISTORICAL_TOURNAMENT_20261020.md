# TORN-FREN overnight split: Windows PC history, isolated VM forward

**Corrected 2026-10-20:** The owner wants six LOCAL PC CPU cores doing
historical backtesting overnight. The VM should keep recording prospective,
as-issued predictions and evaluating matured forward outcomes; it should
NOT run a competing automatically scheduled nightly historical tournament.

The private `nightly-historical-all24.yml` workflow has therefore had its
`schedule` and `push` triggers REMOVED. It is manual-only fallback and
does not consume the VM overnight. The existing separate
`forecast-research.yml` and V160/V161 research / canary services were not
disabled or restarted; their actual successful forward batches still need
verification. The sanitized VM snapshot can lag (one observed sample was
219 seconds old), so a skipped forward capture is not a model failure.

## One-time Windows PC setup

From PowerShell, use an existing checkout of public repository
`fungjkTorn/torn-fren`, **branch**
`research/v38-full-roster-live-prep-20261009`, or clone it:

```powershell
cd "$env:USERPROFILE\Desktop"
git clone --branch research/v38-full-roster-live-prep-20261009 https://github.com/fungjkTorn/torn-fren.git torn-fren-pc
cd .\torn-fren-pc
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install numpy==1.26.4 requests fastapi python-dotenv
```

If the PC has an existing cloned research branch, `git pull` instead
of cloning a second repository. Do not use an older V78 checkout or checkout
an unverified different branch and claim identical model results.

Get a **consistent copy of the sanitized research-only historical stock
database** onto your PC:

```powershell
.\scripts\copy_vm_history_to_pc.ps1
```

This script uses the already known VM SSH key location on the user's PC.
It sends Python's SQLite online backup routine via SSH and
`sudo -n python3 -`, reads ONLY
`/var/lib/torn-fren-research/stock_history_research.db` via SQLite
`mode=ro`, verifies the 24-item sanitized metadata, transfers a
disposable snapshot to `historical_pc_data/stock_history_research.db`,
then removes only the temporary VM transfer copy. If the key path/IP
differs, use `-SshKey` and `-VmHost` parameters. The transfer does not
restart any service, change production collector data, or upload a DB
to GitHub. It does briefly use VM disk/CPU while making the copy.

**Smoke before unattended overnight:**

```powershell
.\.venv\Scripts\python.exe .\scripts\run_pc_historical_sixcore.py --source .\historical_pc_data\stock_history_research.db --smoke --workers 2
```

**Full overnight on the PC, 6 cores:**

```powershell
.\.venv\Scripts\python.exe .\scripts\run_pc_historical_sixcore.py --source .\historical_pc_data\stock_history_research.db --workers 6 --days 6 --output .\historical_pc_results\overnight-24
```

Keep Windows **awake and plugged in**; a sleeping PC cannot finish the
work. Re-run the same command with the same `--output` to resume
successful item reports, without deleting partial logs. Use a new
`--output` directory if the source DB or code commit changes.

## What six CPU processes test

`scripts/run_pc_historical_sixcore.py` is a light orchestrator around
the **existing** `research.restock_event_clock` as-issued 5-minute
historical replay. Each independent subprocess evaluates one of the
exact 24 item keys and can be distributed over six CPU cores. Every item
compares:

- **Four physical restock clock models**:
  `phase_empirical`, `interval_median`, `interval_ridge`,
  `phase_recursive_ridge`.
- **Two flight-window policies each**: expected and conservative bounded.
- The matched `leave_now` control, plus first reachable future restock
  event, stock >=30 at landing through +10s, estimated waiting time, source
  expiry / reissue decisions, and physical restock timing error.
- Chronological development and later validation portions, in the same
  item and forecast periods. Late validation is descriptive, not
  automatically used to promote models.

This is the first **clock tournament**, not a full replication of all
old individual plushie specialist policies, the private V151 paired
candidate, or every Japan-specific model. Later comparisons can add those
competitors on matching frozen test periods once this complete baseline
is measured. Never claim all specialists have been tested if they have not.

Outputs in `historical_pc_results/overnight-24/`:

- `scores.csv`: per-item, per-policy and per-time-slice timing, departure
  coverage, simulated arrival success, paired leave-now outcomes.
- `summary.json`: completed/failed item counts, model/source SHA256,
  immutable report provenance and resource status.
- `items/<item>/result.json`: full per-item model report and statuses.
- `items/<item>/attempt_*/`: saved output/logs for failed or
  interrupted tasks, never silently represented as success.

Data quality: successful global heartbeat and change-only stock records
produce **poll-based outcome proxies**. They do not certify actual player
flights, fresh per-country provider observations or exact game event
seconds. Multiple hourly cohorts can share one physical restock. Source
SQLite is never opened for writing, and its file SHA256 is verified after
the run. The controller refuses output folders with mismatched
source/model SHA. Both data and results are `.gitignore`d. The script
cannot deploy anything to Torn production.

## VM continues true forward work

The VM retains its prospective five-minute schedules and existing
source collectors and specialists; **no second historical overnight
timer runs**. Continue checking `reports/latest_physical_event_forward_status.json`
in the private research repository for *real* as-issued 24-item batches
and matured outcomes. Distinguish no data / stale snapshot / timeouts
from accuracy misses. A shorter research-copy refresh would improve
forward capture coverage, but changing production collectors or ACLs
requires a separate reviewed step; do not bypass permissions.

The aim is to use the PC to optimize and compare historical models,
then verify any winner using truly future-issued VM observations.
No automatic model promotion or production site deployment.
