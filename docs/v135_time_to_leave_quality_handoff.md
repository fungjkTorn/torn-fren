# Time-to-leave research handoff — after V128/130/135

## Confirmed facts
- Original public graph `web/static/index.html` / `services/prediction_v2_live.py` displays observed stock history, next predicted restock window, target arrival window, best departure range, flight countdown, stock lifetime/depletion estimate and reachable P1/P2+ cycles. It is not the 24-item V128 engine.
- Original graph archives restock/cycle outcomes in `forecast_audit_runs` and `forecast_audit_points` when instrumented; original `arrival_hit` means the modeled arrival fell between reconstructed target restock and depletion, NOT necessarily ≥30 stock as observed at landing.
- V75 research historical study showed 154/227 (67.8%) selected-stock arrival proxies versus 169/227 (74.4%) leave-now in an overlapping-cohort targeted test. Not original graph V2 performance or certified player flight outcome.
- V128 is a **single experimental** 24-item empirical HIGH/LOW Monte Carlo restock survival/earliest-arrival challenger with individual country travel times, threshold >=30 at arrival, 128 scenarios, two adjacent five-minute scores >=0.60, <=8h departure horizon. Its 0.60 fraction is NOT calibrated.
- V128's 24-item private five-minute timer has been enabled on user's VM, and the FIRST confirmed run wrote 24 rows at epoch 1791773040. No second batch yet confirmed in conversation. Existing V38 private research timer was active. V128 uses `/var/lib/torn-fren-v38/v128_earliest24_shadow.db`; it does not change the website or old specialists.
- V128 can issue future watches; anything >5min needs fresh near-departure reconfirmation, not GO. Still missing per-country upstream freshness and actual player flight evidence.
- V130 phase-pinned common random numbers for lower Monte Carlo reissue jitter is committed/tested, NOT deployed or substituted.
- Old V131 historical arrival audit was provided; user will run an audit in the morning.

## Latest research additions (GitHub CI green at `0a48218c0fbd48e51d6c056c421de376b47bc521`)

- `research/v132_departure_timing_quality_audit.py`: counts 24-item leave-now/near-term/future-watch/abstain coverage, same-observed-stock departure drift, exact as-issued watch reconfirmation before departure; no writes.
- `research/v133_private_departure_panel.py`: produces a read-only full-24 display contract; distinguishes research near-term, future watch, expired, abstained and incomplete snapshots; does not modify the public graph and never labels a forecast as certified GO or a 0.60 scenario fraction as actual success rate.
- `research/v134_original_graph_v2_audit.py`: reads historical original graph V2 stored restock-window successes, reconstructed target-cycle arrival success and projection-depth metrics from **collector DB in mode=ro**; permits missing original audit tables; no writes.
- `research/v135_morning_departure_brief.py`: one combined compact report covering original graph V2 restock history (30d), V75 old poll-at-arrival (3d), V128 latest (V129) poll-at-arrival/leave-now, V128 timing stability/GO reconfirmation (2d) and per-item coverage. Outcomes remain separated by distinct definitions.
- Tests: `tests/test_v132_*`, `tests/test_v133_*`, `tests/test_v134_*`, `tests/test_v135_*`. Workflow `.github/workflows/v85-japan-forward.yml` passed at pinned commit; see https://github.com/fungjkTorn/torn-fren/actions/runs/38199730948.

## Morning read-only VM audit

From Windows PowerShell SSH into `ubuntu@150.136.108.146` with key `C:\Users\fungb\Desktop\.ssh\torn-fren.key`. Checkout remains `/home/ubuntu/torn-fren-v38-probe` on original HEAD. Fetch research branch; stage immutable source with `git show 0a48218...:research/v{129,131,132,133,134,135}*.py` into `/home/ubuntu/torn-fren-private-models/v128_stage/pinned/research/`. The V128 pinned stage already has all dependency modules. Prepend pinned research to `research.__path__` and import `research.v135_morning_departure_brief`; run `v135.main()` under 240-second `nice -n 15` read-only Python. Do not restart V38, V75, V128 or production. If archived original graph V2 results are unavailable, report explicitly; do not invent accuracy numbers.

## Decisions after evidence

1. Confirm all five-minute V128 snapshots are really being saved (not just a single successful first tick), and preserve unscored/missing items.
2. Score forecast ARRIVALS after they mature using collector's poll brackets with honest uncertainty. Distinct item/hour bins share restocks; not independent.
3. Measure far WATCH -> actual fresh near-departure conversion and departure drift; whether reasonable waits improve matched arrival stock versus leave-now and existing specialist. Don't promote a result just because selected outcomes score high.
4. Compare old original graph V2 forecast restock-window and target-cycle semantics separately from direct ≥30 arrival proxy. A proposed UI can keep old graph/history but show new 'Earliest departure', 'ETA', 'WATCH/near-term', 'Reconfirm required', and evidence tier only once genuinely validated.
5. Don't deploy V130 or switch website/champions without prospective validation and explicit user go-ahead. Later expand beyond 24 to 200+ items with resource safeguards.
