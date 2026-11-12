# V2 / experimental beta integration progress — 12 October 2026

Base: Work's green commit `bae370df7c3c6e2936684245f214cbfeadcdb578`.
Research branch: `research/v38-full-roster-live-prep-20261009`.
All work remains **unmounted and un-deployed**, with no VM/database writes.

## Why this work matters to the user's product

Product question: "What's the earliest sensible time to leave for the next
foreign-stock opportunity I can actually reach, ideally arriving with >=30?"

There are two distinct kinds of model outputs, and they must not be confused:

1. **V2 restock/depletion forecast**: predicts the next restock time
   and a stocked-lifetime interval, plus multiple reachable P1/P2/P3
   forecast cycles; permits a departure-window calculation but does
   **not** itself establish >=30 items at the moment of landing.
2. **Specialist/arrival model**: predicts a departure/arrival candidate
   from historical >=30-at-arrival outcomes. It does **not** inherently
   predict a restock timestamp or a stocked lifetime. Its probability
   or simulation fraction is not independently calibrated.

The original graph should preserve type (1), while the experimental board
shows the associated incumbent type (2). An item can have BOTH without
falsely forcing them to share one restock time.

## New tested integration code

### `research/v2_beta_departure_bridge.py`

`build_item_timeline(item_key,v2,now,issued_at,stock_as_of,incumbent,...)`
accepts an already calculated V2 `predictions` chain in the **actual**
field names of `services/prediction_v2_live.py`; it never queries live data,
rebuilds profiles or runs a champion.

- Uses the shared V141 safe window feasibility guard and per-country PI+pilot
  flight times from the existing `research.plushie_champions.common`.
- Walks V2's P1..P8 projected sequence and skips impossible or expired cycles.
- Picks the **first reachable departure** from the remaining cycles. An
  unreachable P1 can yield reachable P2; returns all qualifying cycles.
- Keeps raw next predicted restock of P1 **separate** even if a later
  cycle is the reachable departure candidate.
- Applies 8h issued departure horizon and 5min as-issued recheck period.
- Fails closed for expired/future issuance, source heartbeat older than
  180s, wrong country travel duration, duplicate/unsorted cycles, mismatched
  incumbent item identity, and incomplete forecast geometry.
- Returns separate `incumbent_specialist` and `first_reachable` fields.
  Does not silently choose generic V128 over the incumbent.
- Labels every V2 departure provisional and sets
  `estimated_stock_at_arrival_30_or_more=None`. Never claims exact game
  stock or calibrated probabilities.

### `research/v2_native_specialist_adapter.py`

Inspection of **real repository source** confirms that
`services/plushie_flower_dynamic_planner_v18.py`, `v19.py`, `v20.py`
their `plan()` output includes:
`query_time`, `departure_time`, `arrival_time`,
`probability`, `support` (and a `robust_probability` in V20).

It is an **arrival-selection model**, not a next-restock timestamp.

`preview_record(...)` safely converts an ALREADY-computed native plan into
the existing V97/V140 `RESEARCH_PREVIEW_*` shape without executing heavy
training, touching data, or asserting gameplay accuracy. It checks:
- pinned country:item, family/config match;
- as-issued query time, stock evidence freshness <=180s;
- exactly correct country flight time and 5-minute departure grid;
- <=8h horizon and numeric, finite 0..1 raw score;
- appropriate 5-minute snapshot expiration.
- `actionable=False`, `prediction_accuracy_verified=False`,
  `probability_calibrated=False`, despite exposing a provisional
  departure on the existing PREVIEW path.

### Tests

- `tests/test_v2_beta_departure_bridge.py`: P1 missed -> P2 usable,
  depart-now, wrong country flight, no data, stale or expired, impossible
  or unsorted cycles, mismatched specialist identity, 8h boundary and exact
  24-item roster.
- `tests/test_v2_native_specialist_adapter.py`: native V18/V19/V20 output
  parity, 16 supported model config identities, separate Japan/champion
  unsupported classifications, preview interface, false GO prevention,
  stale/future/invalid candidate rejection and shared timeline compatibility.
- GitHub Actions `.github/workflows/v85-japan-forward.yml` runs both tests.
- Existing 72+ previous Work regression tests for stale-UI behavior remain.

## Accurate current model integration inventory

Derived from `research/v38_roster.json`, `v128_full24_earliest_shadow.py`,
and confirmed source functions in this repository:

| Code capability | Items | Meaning |
|---|---:|---|
| Existing native V18/V19/V20 `plan()` departure/arrival outputs | 16/24 | Their raw outputs can now be normalized to beta-preview semantics, **without recalculating the plan** |
| Archived selected plushie champion bundle wrappers | 7/24 | Reproduction modules mainly provide `replay(db)` or `replay_target(db,...)`; no independently verified deployed live plan bridge from those wrapper files |
| Separate Japan Xanax specialist | 1/24 | Live inference source and deployed mapping remain to be confirmed |
| **Verified live end-to-end website model mapping** | **0/24 inspected here** | Means UNKNOWN from this conversation, not necessarily that models are absent on the VM |
| **Measured real post-issue >=30 landing success** | **UNKNOWN** | Requires the pending private VM forward audit |

**Important nuance:** The native adapter supports 16 model-family/config
identities, not 16 newly verified live predictions. It is a conversion
interface, not a deployment of those planners. The seven archived champion
wrappers may rely on common historical context/planner code for actual
inference; inspect that service wiring rather than declaring they lack all
inference implementations.

## New optional direct connection into the EXISTING V2 API (research only)

The research-branch `services/prediction_v2_live.py` now stamps
`forecast_model_computed_at` exactly when its actual model computation
completes. This timestamp survives result caching and is **not** refreshed
by each successful web request. It is distinct from archival audit timing
and from `prediction_v2_checked_at`, which reflects only response checks.

The existing `web/app.py` `/api/history` optionally provides
`analysis.beta_item_timeline` when environment variable
`TORN_FREN_V2_BETA_TIMELINE=1`. The default is OFF; without the flag
the API response keeps its original shape. The preview reuses the
already-calculated `prediction_v2`, collector heartbeat and frozen model
issue stamp; **it does not compute a second expensive prediction**.
No HTTP route or external API calls are introduced.

The field contains the provisional reachable P1/P2+ candidate, all other
usable projected cycles, the unchanged first-restock forecast,
refresh deadline, and explicit lack of certified >=30 stock at landing.
If forecast issuance is missing or stale, it returns a reason and no
suggested departure. No existing deployed experimental page is modified.

`tests/test_v2_beta_history_preview.py` verifies OFF by default, first
reachable P2 with P1 missed, model issue time not renewed by HTTP refresh,
freshness withdrawal, malformed data fail-closed and that the base stock
history still renders.

**This is a research branch candidate, not installed on VM**. Before
enabling on the deployed website, reconcile the actual VM source and test a
reversible staged canary. This option alone does not finish integrating
the original deployed `/experimental` source.

## Integration steps remaining

1. **Do not deploy yet.** Obtain original deployed `/experimental`
   Python/HTML and V41 API from VM safely, as
   `docs/home_vm_actions_20261012.md` instructs. The research
   `web/app.py` does NOT contain the full deployed experimental routes.
2. Verify real V75/V128 issue/valid_until, item identities and incumbent
   source provenance, not just availability of a source file in the repo.
3. Plumb the already-existing per-item V18–V20 decisions through this
   converter **after** inspecting the deployed model worker's true output.
   Never fit those expensive models in an HTTP request.
4. For the 7 specialist champion mappings and Japan Xanax, identify the
   actual deployed runtime worker and adapt its *recorded* output into the
   same arrival-candidate fields.
5. Add a shared, separately versioned forecast API contract for both views
   behind a default-off experiment and strict source/freshness checks.
6. Run V139 original V2 vs V75/V128 arrival outcome audit on VM, distinguishing
   success, miss, unknown and not yet matured. **Still not run.**
7. Compare actual issued-time accuracy and WATCH reconfirmation per item;
   promote only proven specialists or boundary models with rollback.
8. Browser QA on BOTH original / graph and EXISTING /experimental. Rollout
   needs explicit user approval, on-site source reconciliation, and rollback.

## Preserved commands

NO new at-home commands are needed. The existing three commands in
`docs/home_vm_actions_20261012.md` (V128 timer health, V139 accuracy audit,
V142 existing page inspection) remain exactly as previously saved.
