# Dual-view beta progress — 12 October 2026

Base: `2581975e3a2602fc2d16180aae6eff72115783ea` on
`research/v38-full-roster-live-prep-20261009`. Candidate code only; no rollout.

## Changes and user-facing effect

- The original V2 history response no longer resurrects the old baseline when
  V2 has no feasible target or its computation fails. Baseline diagnostics,
  observed stock history and profitability remain available.
- The existing graph ticker withdraws guidance immediately after a failed
  refresh, while a forecast refresh is pending, after 300 seconds without a
  newly checked response, or when collector heartbeat evidence is missing,
  future-dated or older than 180 seconds. The last graph remains visible.
  A successful fresh response restores modeled guidance. Cached chart redraws
  do not renew this validity deadline.
- `prediction_v2_checked_at` is the server's response check time. It is NOT
  model issuance, a new forecast, or proof of fresh per-country stock. Existing
  model timestamps are untouched. Freshness gates are necessary conditions,
  not a certification that at least 30 items will remain at landing.
- The open graph window says MODELED DEPARTURE WINDOW with that limitation,
  replacing the overly strong GOOD TO LEAVE label. Forecast cycles, chart
  layout, PI+pilot times, restock bands and countdown behavior are preserved.
- The existing non-mounted V140 board adapter reevaluates V128 WATCH/near-term,
  expired, passed and invalid/future issue labels at read time. It never renews
  issuance or replaces an incumbent with V128. No extra dashboard was created.

## Verification

72 local tests passed across the new API/JavaScript/board regressions and
existing V97, V133, V140–V143, V38 API/cache/revision and profitability suites.
The new suite executes the actual ticker/helper JavaScript in Node, checking
failed refresh withdrawal, recovery, frozen-page expiry and boundary clocks.
API tests isolate model failures without accessing any collector database.
The research CI workflow now includes the new regression suite.

These are synthetic software tests, not measured stock-prediction accuracy.
Rendered desktop/mobile QA and deployed-source reconciliation remain pending.

## Per-item evidence matrix

Derived from `exact_roster()` without changing any model or verification flag.
“Recorded source flag” repeats repository metadata, not fresh certification
of the model currently running on the VM. Every deployed mapping, per-country
freshness state, and forward-arrival result below is **UNKNOWN** until VM
evidence is provided. Preview means the existing three-item opt-in cohort.

| Item key | Incumbent family / config | Recorded source flag | Preview | Live/arrival evidence |
|---|---|---|---|---|
| arg:Ceibo Flower | V18 / dyn3 | true | no | UNKNOWN |
| arg:Monkey Plushie | online_template_expert | false | no | UNKNOWN |
| can:Crocus | V18 / dyn5 | true | no | UNKNOWN |
| can:Wolverine Plushie | V18 / dyn8 | true | no | UNKNOWN |
| can:Xanax | V19 / dyn8 | true | no | UNKNOWN |
| cay:Banana Orchid | V18 / dyn7 | true | no | UNKNOWN |
| cay:Stingray Plushie | V18 / dyn7 | true | no | UNKNOWN |
| chi:Panda Plushie | two_expert_extra_trees | false | yes | UNKNOWN |
| chi:Peony | V20 / traj12 | true | no | UNKNOWN |
| haw:Orchid | V18 / dyn3 | true | no | UNKNOWN |
| jap:Cherry Blossom | V19 / dyn2 | true | no | UNKNOWN |
| jap:Xanax | japan_xanax_specialist | false | yes | UNKNOWN |
| mex:Dahlia | V18 / dyn2 | true | no | UNKNOWN |
| mex:Jaguar Plushie | V18 / dyn3 | true | no | UNKNOWN |
| sou:African Violet | V19 / dyn7 | true | no | UNKNOWN |
| sou:Lion Plushie | two_expert_logistic | false | yes | UNKNOWN |
| swi:Chamois Plushie | online_template_expert | false | no | UNKNOWN |
| swi:Edelweiss | V19 / dyn9 | true | no | UNKNOWN |
| uae:Camel Plushie | template_probability_selector | false | no | UNKNOWN |
| uae:Tribulus Omanense | V18 / dyn3 | true | no | UNKNOWN |
| uni:Heather | V18 / dyn3 | true | no | UNKNOWN |
| uni:Nessie Plushie | recent_phase_template | false | no | UNKNOWN |
| uni:Red Fox Plushie | global_regime_analog | false | no | UNKNOWN |
| uni:Xanax | V19 / dyn3 | true | no | UNKNOWN |

## Integration gates and rollback

1. Keep the three commands in `docs/home_vm_actions_20261012.md` exactly as
   saved. They are not executed by this work. The timer check, V139 outcome
   audit and V142 deployed-page probe are still required.
2. V142 fingerprints and route checks are a preflight, not the deployed source
   itself. Obtain the actual relevant deployed Python and HTML for comparison
   before preparing a merge patch. Do not copy research `web/app.py` over it.
3. Build the patch against that captured source; record expected before/after
   SHA256 hashes of each touched file. Abort if any live file differs from its
   expected before hash. Preserve the original `/experimental` routes and HTML.
4. Test a separate local/canary instance using captured source and sanitized
   fixtures; gate public routing behind a default-off flag. Confirm exact 24
   identities, incumbent labels, filters, graph links, both screen sizes,
   offline/expiry behavior, P1/P2 rollover, and bounded request latency.
5. Only after that evidence and explicit rollout approval: retain exact
   pre-change web-file backups and service configuration, enable the canary
   for the agreed cohort, and verify both views. Do not alter collectors,
   model selection, timers, or private ledgers as part of the web change.
6. On failed health/behavior checks, disable the canary and restore only the
   captured web changes. Verify restored hashes and both original routes.
   Concrete rollout commands must be generated from the observed VM state;
   a generic whole-file replacement would discard deployed functionality.

## Next highest-impact work

Use V139's real as-issued outcomes to identify which incumbent/V2 restock or
stock-duration errors cause missed >=30 arrivals, and fix those measured
causes. Integrate the tested display changes into the actual existing board
and graph after source reconciliation. Do not start another broad tournament
or declare the 24-item beta ready from these tests alone.
