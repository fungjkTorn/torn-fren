# V38 CPU recovery: source-versioned caching before 21/236-model rollout

2026-10-09 | Research only | No production deployments

## Root-cause attribution (operator-provided live VM)

2 OCPU Oracle VM, no swap, ~10 GiB RAM available, ~0% disk I/O wait.
System load ~3.67–3.93, CPU busy 97–100%, CPU pressure some
avg10~50%. These conditions **block** new read-only research probes.
The collector remains healthy: recent loops 0.7–6.6 seconds, latest
heartbeat 9 seconds. This is not a reason to upgrade the VM yet.

- PID 3860 (cgroup /system.slice/torn-fren-poller.service):
  `/opt/torn-fren/venv/bin/python /opt/torn-fren/poller.py`,
  average **94.1% CPU**, multiple CPU-heavy Python threads despite
  poll loop mostly sleeping. Likely routine background prediction
  auditing plus startup refresh, not expensive recovery processing;
  exact per-function profiling still needed.
- PID 760 (cgroup /system.slice/torn-fren-web.service):
  `uvicorn web.app:app --host 127.0.0.1 --port 8000`, average
  **58.4% CPU**, with background graph/prediction tasks.
- Separate gap-recovery service has completed its real backlog and
  returned to inactive. Shadow-capture service being inactive is normal
  for its timer-triggered oneshot; original shadow timer stayed enabled.

## Proven repeated work in V37 source

`web/app.py` has **20s** cache TTL for both graph analysis and
V2 predictions (`_ANALYSIS_CACHE_TTL_SECONDS` and
`_PREDICTION_CACHE_TTL_SECONDS`). After TTL expiry, another
background worker can rebuild every item's old cycles and
forecast data; repeated graph requests for unchanged stock can trigger
up to ~15 times more historical calculations than 5-minute bucketing.
This is an upper bound on refresh count reduction, NOT an established
real-world CPU or latency improvement.

Independently, `poller.py:_audit_worker` processes a coalesced set of
changed items and `_run_item_audits` calls older prediction audits,
`resolve_forecast_audits`, `build_live_prediction_v2`, and Japan
shadow auditing. Both processes reconstruct qualifying historical
cycles. This is independent work in separate processes; a web
in-memory cache alone cannot fix poller CPU saturation.

## New research-only opt-in V38 website source revision cache

`web/v38_revision_fingerprint.py` constructs a per-item key from:
- current stock row timestamp/quantity/cost/source (already read for
  `/api/history`);
- `collection_gaps` MAX id and MAX end timestamp;
- UTC five-minute planning clock bucket.

It **requires successful collector heartbeat within 180 seconds**.
Missing/unverifiable/stale/future collector or future item data fails
closed: do not present a stale stock-state forecast as current.
Uses independent read-only SQLite and explicitly closes handles.

`web/app.py` exposes opt-in flag
`TORN_FREN_V38_REVISION_CACHE=1` (default is OFF):
- Within unchanged source revision and five-minute slot, reuse a
  previously computed graph-analysis/V2 result without triggering
  more expensive background work. Existing
  `_roll_prediction_to_now` still updates departure reachability as
  clock time passes.
- On material stock/cost/source change, known-gap revision, or new
  five-minute planning slot, queue a refreshed expensive calculation.
- Do not return a superseded revision as fresh while a worker runs.
  Mark it warming; retain stock-history API when no current
  prediction is available.
- All revisions are for the *one* item; nearby item changes don't
  invalidate all 236 cached models.
- Existing website V2 behavior is untouched unless flag explicitly
  enabled, and production V37 is not modified.

Regression `tests/test_v38_revision_fingerprint.py` covers stable
items, changes, new gaps/end-of-gap, missing/future/stale source,
single-flight 30 repeated model requests and graph response-shape
parity. CI V38 expanded adapters green as of source cache commit
`f156a717` (verify latest HEAD before promotion).

## Next major performance work

1. **Measure and separate regular poller audits.** Preserve
   `forecast_audit_points` provenance, censored states and exact
   completed-restock scoring. Don't suppress pending outcomes silently.
   Move expensive regular V2 audit recomputation to resource-capped
   isolated workers, and use a durable dirty-item queue.
2. Precompute validated completed-cycle features **once per actual
   source/gap revision**, reusing immutable history across web, shadow,
   and forecast-audit workers. Cache construction must remain as-of-time
   causal, filter known collection gaps, and version schema/algorithm.
3. Event cadence: stock collection stays 30s; active candidate selection
   runs five-minute cadence and reacts to material zero/restock state.
   Cold rare items can use 30m watch intervals only when not actionable
   and after their source evidence is up-to-date; do not silently miss
   a five-minute replanning obligation for active items.
4. Publish a bounded latest-prediction snapshot to a **separate SQLite
   sidecar**, read-only for the public app. The V38 research sidecar
   schema already exists. Expired, skipped, error, future-source
   and missing model results are visibly abstained or use original V2
   fallback, never mislabelled as an original specialist.
5. Admit batches only after actual VM headroom (load1<=1.6 on 2
   OCPUs). Benchmark pre/post CPU pressure and p95
   `/api/history`/`/api/catalog` latency, collector heartbeat and
   FD counts. Favor same hardware and durable rollbacks. Never use
   aggressive cache TTLs that obscure a real stock change or a gap.

## Environment/deployment boundary

No production `profitability-v1` SHA, systemd units, API flags or
stock DB were changed by these research commits. V37 collector safety
`a93879d` remains the operational release. The V38 research branch
has much more code than this feature, so **do not fast-forward
production to the V38 branch**. If measurements warrant a release,
port only verified website cache and audit throttling to a
separate small V37-derived patch with operator-approved backup,
health measurements and rollback.
