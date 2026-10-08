# V32 checkpoint — prospective evidence capture and production-readiness decision

**Date:** October 8, 2026. **Do not merge to main or enable public champions.** All changes remain on `research/v32-prospective-outcome-gates`, based on V31 draft research.

## What passed

- Verified source-aligned research reproducibility, previously 132/132 saved departures across four disputed items. This was **compatibility-port exact-decision parity**, not full original native execution and NOT 132 stock successes.
- V31 read-only private single-tick generic inference, check-summed frozen masters, heartbeat/gap/future-data protection, 35s child timeout, V2 fallback/rollback flags; research-only, never public guidance.
- V32 discovered and **fixed a real INSERT positional bug** in V31 evidence capture: `source_schema` and `source_generated_at` values were swapped. V32 regression test reads those two SQLite columns, verifying proper order. No production evidence capture had been deployed; previous synthetic data should be discarded.
- V32 `research/v32_score_shadow.py` opens the collector and V31 evidence SQLite **read-only**. It only scores a private proposal after a complete maturity horizon, checking near-arrival pre/post stock observation freshness, successful poll heartbeats, absence of known collection gaps and transition ambiguity. Missed proposals remain failures for coverage, not excluded successes. A proposal with departure already passed at evidence capture is also an explicit MISS, not a dropped denominator. V2 is scored on the same matured sessions and under the same conservative stock-bracketing rule.
- Travel times corrected to original `services.arrival_success_lab.TRAVEL_SECONDS` values (PI and airstrip).
- V32 `research/v32_capture_pilot.py` is an explicitly opt-in, local loopback-only **one-pass** HTTP reader, max four research items/invocation, with private token in request headers and only whitelisted safe columns persisted to separate SQLite. No scheduler, no gameplay, no player API.
- `research/v32_catalog_release_report.py` creates a row for all 236 provisional item candidates; missing genuinely prospective observations remain **NULL/not measured**, not fabricated 0%; every model stays blocked pending native parity, independent resolved stock windows, forward success, tested rollback.
- V32 GitHub Actions checks above on synthetic fixture datasets. **No on-VM or collector production integration has yet been performed.**

## Test/release ledger

All 236 research items:
- 162 generic model configurations complete from frozen V19/20/21 files.
- 21 museum flower/plushie research entries, including seven item-specific plushie source policies.
- Japan Xanax specialist separately reserved and not integrated.
- After Oct 5 cutoff on already-analyzed Oct 8 archive: 1,772 completed stock opportunities across 236 item keys, but only 47 keys have >=8 observed windows. These are not forward prediction wins.

Artifacts in research chat:
- `TORN_V32_236_Item_Research_Scoreboard.xlsx` — filterable 236-item dashboard plus seven plushie comparisons.
- `TORN_V32_236_Item_Research_Scoreboard.csv` — raw research scoreboard.
- `V31_236_Independent_Stock_Window_Readiness.csv` — retrospective observation opportunities.

## Deployment prerequisites in order

1. **GitHub check:** V32 + parent PRs stay DRAFT, main untouched, no model routing changes until hard release gates pass. Native V18/V19 original engine must run against exact archived `fresh(4).db` SHA `9f39d40e4f255d310ea0a4e20a68d179af2ec145f7b43a02faf10a03d1359761` with exact saved configs, complete holdout start tracking and no lookahead.
2. **Private VM trial:** Require user-authorized credentials to the existing host. Deploy ONLY a private, localhost-facing research endpoint first. Preserve V2 public route unchanged; flags default OFF. DO NOT print private token/keys; don't commit database or config files. Verify absence of public access, collector SQLite write protection, proper 404/403, V2 fallback, response latency, rollback by disabling flags.
3. **Forward freeze:** Assign a fixed experiment ID and timestamp/config hashes BEFORE gathering new stock; start the opt-in V32 loopback capture at a bounded cadence. Do not retroactively choose favorable models, starts or time ranges.
4. **Independent validation:** Score all eligible captured departure starts after arrivals mature. No recommendation counts against coverage. Maintain observation-gap/uncertain outcomes separate; group predictions by **distinct resolved restock stock windows** so overlapping start ticks do not masquerade as independent trials.
5. **Graduated live release:** Promote item by item only with independently confirmed native parity, causal prefix invariance, >=30 genuinely prospective eligible starts, >=8 distinct *qualified* stock windows, >=95% coverage, >=90% successful arrivals (or explicitly cautioned provisional 75% floors for Monkey/Chamois/Camel), passed V2 fallback and tested flag rollback. Never show uncalibrated trip-success probabilities. Pilot first, production only after full release approval.
6. **Scale:** 236-item public champion prediction with specialist architectures is NOT ready. Current V31 single-tick worker supports generic model families only, no specialist live adapters and no resilient batch queue/operational supervision for 236 items. Do not enable 236 concurrent costly planners.

## Private pilot example — documentation only, NOT executed

From repository root on an isolated host with the DRAFT research branch and private environment configured:

```bash
# Only after actual VM staging authorization, source checksum checks,
# and private route/tokens already set up; never run against public API:
python -m research.v32_capture_pilot \
  --endpoint http://127.0.0.1:8000 \
  --item 'can:Fire Hydrant' \
  --item 'arg:Cannabis' \
  --evidence-db data/private_shadow_evidence_v32.db \
  --experiment v32-pilot-20261008 \
  --acknowledge-private-research
```

Do not invent a live validation rate now: no private postfreeze capture exists in the original user-provided archive. No VM credentials are connected in this chat. No direct future-data feed is available in the tools. Production release is still blocked; a new independently collected snapshot, exact native runner and a controlled authenticated VM stage are mandatory.

## Final V32 addendum

- V32 PR #8 remains draft, targeting the V31 research branch, not main.
- Strict evidence maturity, late/invalid departure failures, and matched V2-versus-challenger denominators are CI-tested.
- V31 parent branch was also patched with the timestamp-vs-schema column-order fix and a regression test; V32 contains the same correction.
- The user-visible 236-item research scoreboard is provided as XLSX, CSV, and a self-contained searchable HTML table. **All 236 statuses are NOT CERTIFIED**. Historical rates exist for 152 items, others are unmeasured or have incomplete evidence; the research tables should never be marketed as measured production win rates.
- Workflow passing does not establish field performance: no on-VM capture, no new postfreeze outcomes, no independent complete event certification, and the specialist adapters are incomplete. Staged research only.
