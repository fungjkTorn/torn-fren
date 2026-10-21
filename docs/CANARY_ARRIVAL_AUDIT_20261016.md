# Retain and audit actual canary publications

The owner started canary source `00bbfa9355bcb76954feefae2b6d8c930c68426a` on October 16. The supplied log contains 358 completed repeating builds, median 10.92sec, range 10.67–12.89sec, no reported publish failures. Startup source age was 33sec. Screenshots show all three views and 13 current proposals among 24 rows. These establish operation, not prediction success.

The initial canary replaces `shared.json`. Its console log does not retain individual plans, so those past publications cannot be scored as a prospective canary trial. Historical reconstruction must remain labeled historical.

## Independent recorder

`research/canary_arrival_audit.py record` polls only fixed localhost:8770 health and board APIs every two seconds, retaining the first received version of each item/issue in a separate SQLite journal. It checks the exact live canary source pin, source freshness and target/depletion/flight contract. Existing issues are never replaced by later readings. It performs no fitting, source database reads or writes, canary restart, game actions, or website changes. The default bounded run lasts eight hours and needs no additional dependencies.

Every observed issue retains all 24 rows, including disabled, abstaining, and already expired plans. An otherwise actionable plan received after its deadline is recorded as an abstention. The frozen simulated departure is the later of reception and the displayed departure. Landing is that time plus the published flight duration. The outcome is sampled stock >=30 from landing through the existing 10-second evidence interval, not an invented exact purchase.

Keep the existing canary process running. Use a separate pinned auxiliary checkout for this script, preserving the running checkout and model source. Example once in the auxiliary checkout:

```bash
PYTHONDONTWRITEBYTECODE=1 python3.12 -m research.canary_arrival_audit record \
  --journal "$HOME/torn-fren-canary-arrival-20261016.sqlite" \
  --expected-sha 00bbfa9355bcb76954feefae2b6d8c930c68426a \
  --duration-seconds 28800
```

The first successful capture prints `PLANS_RECORDED` with 24 rows. `CAPTURE_UNAVAILABLE` is a failure to collect, not a success observation. No claim is made about unobserved publications; interruptions must be reviewed in the recorder log. The recorder can run under `nohup` for the bounded eight-hour session, but it cannot keep the separate foreground canary alive if its process exits.

## Score as soon as outcomes mature

Use the existing canary NumPy venv to run the scorer from the auxiliary checkout:

```bash
OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  "$HOME/torn-fren-shared-canary-00bbfa9355bc/.venv/bin/python" \
  -m research.canary_arrival_audit score \
  --source /opt/torn-fren/data/stock_history.db \
  --journal "$HOME/torn-fren-canary-arrival-20261016.sqlite" --compact
```

Scoring uses one read-only source transaction and the existing `ArrivalEvidence` implementation. It waits until landing +10sec +180sec maturity, respects successful poll brackets, collection gaps, provider changes and threshold transitions, and reports unknown evidence separately. It never modifies the collector or journal and explicitly pins the auxiliary checkout's research imports. Earliest outcomes become scorable after the shortest offered flight plus roughly 3min10sec; long flights need their own full duration. Waiting until tomorrow is not a scoring requirement.

Primary counts select the first observed issue per item/UTC hour **before** filtering proposals or outcomes. All observed publications are retained as a secondary diagnostic. Both are correlated observations, not independent trials or calibrated success probabilities. Future plans are separately counted in the full JSON report: their hypothetical stock outcome does not prove a future reconfirmation would succeed. Success, failure, unknown, pending and abstention remain distinct. Restock and depletion timing accuracy are not measured by this arrival audit.

Run without `--compact` for full per-item results, including immediate/future breakdowns, unknown reasons and diagnostic counts. Review minimum sample size, proposal coverage, missingness and repeated-cycle correlation before changing assignments. Keep the existing Chamois and Camel fixed forward experiments and their model pins unchanged.
