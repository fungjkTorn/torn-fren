# TORN-FREN — MASTER HANDOFF FOR WORK MODE
**Prepared:** Monday, 12 October 2026
**Audience:** Next ChatGPT Work session in the TORN Projects project
**Repository:** https://github.com/fungjkTorn/torn-fren
**Active isolated branch:** research/v38-full-roster-live-prep-20261009
**Last verified branch head before this handoff:** c9091bd69e1225060eaddcc072d70f175b9c0990
**Verified CI at that head:** https://github.com/fungjkTorn/torn-fren/actions/runs/38284457908 — completed, SUCCESS.

## 0. START HERE — instruction to the next Work session

We have spent weeks researching Torn foreign-stock travel forecasting. The user recently clarified that **the original Prediction V2 website was and remains the product they wanted**. Research was supposed to fix V2's prediction accuracy and time-to-depart errors, not replace the product with an ever-growing isolated model tournament.

**The user's latest, explicit decisions:**
1. KEEP BOTH EXISTING USER INTERFACES:
   - **/experimental**: multi-item list/board to compare many stock opportunities at once. Show item, selected model, time until departure, arrival time, prediction issue/expiry/refresh deadline, and provisional WATCH versus near-term status.
   - **/** (original V2 graph): detailed single-item graph with observed foreign stock, projected restock/depletion cycles, uncertainty windows, flight duration and departure countdown.
2. Improve the shared forecast engine. The existing champions, V75/V128 research, graph, and beta page are valuable; do **not** discard them or invent a replacement UI.
3. Finish and validate the **24-item beta**. This should have happened already; the user is disappointed that extensive experiments did not reach the intended product.
4. After a reliable shared forecast platform, build the **Torn Travel Assistant**: plan a day of profitable trips around predicted restocks, flight lengths, current stock, potential wait times and profit per unit of time. It should help the player plan, not automatically fly or buy.
5. Do as much independently as Work can: read GitHub, inspect code, run tests and safe workflows, implement end-to-end improvements on the research branch, and use connected applications/browser/computer where actually available. Avoid asking the user to run commands until necessary. The user is away from their PC; their previously postponed VM commands are listed below.
6. Preserve production and data. Do NOT change live Torn gameplay, production website, active timers, V38/V75/V128 recorders, collector DB, deployed source, or model champions without an explicit rollout decision and verified reversible plan.

**Work should not start by re-running broad model tournaments or incrementing version numbers just to generate more experiments.** Every change must improve a specific V2/experimental field or user decision, have tests, and be measured against frozen forward evidence.

## 1. What the desired final product does

### A. Existing /experimental multi-item dashboard

The deployed VM has historically served **/experimental** and **/api/experimental/v41/predictions**. The GitHub research checkout does **not** contain the complete deployed implementation, so never overwrite it from research before obtaining the actual deployed source.

The board should make it easy to scan items/countries, sort/filter departures, and tell:
- Item / destination / category (flowers, plushies, medical; eventually fossils and all catalog items).
- Which per-item **incumbent specialist/champion** is being used; option to inspect experimental challengers separately.
- Latest observed stock with source freshness evidence, if verified.
- Predicted next restock window and/or >=30-at-arrival candidate, labeled by model output type; do not fake a restock timestamp from a simulation arrival score.
- Leave in / earliest departure / reasonable departure window, expected arrival/ETA, destination's PI + pilot flight duration, estimated stock cushion only where supported.
- Issued time, valid-until time, next refresh/reconfirmation due, expired/stale/unknown state.
- READY NOW / DEPART SOON / WATCH / EXPIRED / ABSTAINED, clearly provisional unless game/provider evidence is independently validated.
- Direct navigation to the existing detailed V2 item graph, preserving filters and item selection.
- An explicit explanation when the experimental forecast differs from original V2 restock-window guidance.

**Do not introduce a second duplicate dashboard.** Build on the existing /experimental implementation and its API contract.

### B. Original detailed V2 graph

Current research checkout files:
- services/prediction_v2_live.py — forecasts restock/depletion and P1/P2+ cycle chain.
- web/app.py — FastAPI, non-blocking /api/history response, caches, clock-only re-selection.
- web/static/index.html — Chart.js detailed graph, old markers, predicted windows and flight ticker.

V2 currently:
- When depleted, anchors to an observed depletion and predicts a waiting time to next restock, including a forecast range.
- When active stock remains, forecasts the next cycle based on estimated stocked lifetime followed by zero-to-restock wait; Japan Xanax has specialized active-sellout blending.
- Projects P1/P2/... cycles up to a bounded ~12-hour forecast horizon, rolling away from unreachable earlier cycles.
- Derives earliest conservative arrival from max(recommended arrival, later predicted restock-window edge), and latest arrival from estimated depletion minus a 60–300-second buffer; subtracts PI + pilot flight time to form departure range.
- Has TOO EARLY, GOOD TO LEAVE, LATE and related timer states.
- **Observed defect:** if predicted depletion is before the conservative arrival lower bound, old browser/server behavior could collapse an impossible interval to a fabricated zero-width 'GOOD TO LEAVE' opportunity. V141/V143 provide a research-only fix in both browser and server, including stale-target clearing.
- **Another product gap:** V2's current-stock reachability Boolean estimates whether depletion occurs after a hypothetical now-flight. Nonzero stock or reaching before theoretical depletion does NOT establish >=30 stock at arrival.

### C. Shared forecasting engine, then travel planner

Maintain a shared, explicit, versioned contract with item key, model/config, prediction issued time, input/source as-of, freshness/expiry, observed phase/qty, forecast restock band, predicted stocked-availability intervals, predicted depletion, minimum threshold 30 arrival condition, departure/arrival suggestions, certainty/evidence labels and revision reason.

Use a **specialist where validated**, fallback statistical model where data supports, and explicit NO FORECAST where not. Do not start 200 heavy model refits on every HTTP request. Use a bounded, separately refreshed cache/worker with efficient indexed queries.

The later Travel Assistant consumes those SAME snapshots, evaluates alternate trips, travel and return flight time, opportunity costs, profitability per player-hour, and replans as stocks change. **No automatic Torn gameplay.**

## 2. Fixed decision contract and accuracy criteria

- Initially **exactly 24 user-selected foreign stock items** (list below).
- Replan **every 5 minutes**, preserving as-issued forecasts and no lookahead.
- Consider departure times up to **8 hours** ahead (experimental V128; original V2 may have longer projected cycle displays).
- Distinguish flight time by destination; PI + pilot travel used by existing scripts.
- A usable modeled arrival aims for **at least 30 units** at estimated landing; existing replay uses **+10-second grace**.
- A future proposed departure is a WATCH, not guaranteed GO: reevaluate close to departure. Snapshot's five-minute TTL is NOT a guarantee a departure six hours away remains good.
- V128 uses 128 simulations, with raw scenario availability fraction >=0.60 at two adjacent five-minute candidates. This is an UNCALIBRATED simulation score, not a 60% real-world success probability.
- Compare next-restock timing error, stocked interval/depletion error, predicted band coverage/width, departures accepted/abstained, observed >=30-at-arrival proxy versus same-issue leave-now, watch->near-term reconfirmation, and same-source forecast jitter; count independent restock cycles separately from correlated five-minute reissues.
- Do not call an observation a confirmed landing without direct evidence. Global collector heartbeats do not prove per-country provider feed freshness. Missing arrival brackets must remain UNKNOWN/PENDING, not a failure or a success.
- User wants more accurate, earliest reasonable departure recommendations, not the highest-looking offline score with impractical waits.

## 3. Exact 24-item roster and model distinction

The source-of-truth partial roster is research/v38_roster.json (22 entries), with research/v128_full24_earliest_shadow.py adding **can:Xanax** (V19 dyn8) and **uni:Xanax** (V19 dyn3).

| Country | Item | Recorded research incumbent/model family |
| --- | --- | --- |
| Argentina | Ceibo Flower | V18 dyn3 |
| Argentina | Monkey Plushie | online_template_expert / checkpoint4_online_selector |
| Canada | Crocus | V18 dyn5 |
| Canada | Wolverine Plushie | V18 dyn8 |
| Canada | Xanax | V19 dyn8 (additional pinned V128 roster entry) |
| Cayman Islands | Banana Orchid | V18 dyn7 |
| Cayman Islands | Stingray Plushie | V18 dyn7 |
| China | Panda Plushie | two_expert_extra_trees / panda_pair_selector_ml |
| China | Peony | V20 traj12 |
| Hawaii | Orchid | V18 dyn3 |
| Japan | Cherry Blossom | V19 dyn2 |
| Japan | Xanax | independent Japan Xanax specialist; source verification incomplete |
| Mexico | Dahlia | V18 dyn2 |
| Mexico | Jaguar Plushie | V18 dyn3 |
| South Africa | African Violet | V19 dyn7 |
| South Africa | Lion Plushie | two_expert_logistic / lion_pair_selector_ml |
| Switzerland | Chamois Plushie | online_template_expert / checkpoint4_online_selector |
| Switzerland | Edelweiss | V19 dyn9 |
| UAE | Camel Plushie | template_probability_selector / camel_fast_selector |
| UAE | Tribulus Omanense | V18 dyn3 |
| UK | Heather | V18 dyn3 |
| UK | Nessie Plushie | recent_phase_template / recent_phase_select |
| UK | Red Fox Plushie | global_regime_analog / rf_localgrid |
| UK | Xanax | V19 dyn3 (additional pinned V128 roster entry) |

**Important:** Several champions are marked source_verified=false in research/v38_roster.json; this is not proof that they are absent from VM. Do not silently mark all champions production-certified.

The six archived champion implementations live under research/plushie_champions/ and use helper modules. Important historic research for Nessie/Red Fox/Lion/Panda/Monkey/Chamois/Camel must not be thrown away. V128 is a generic challenger and must NOT automatically replace any of those specialist incumbents.

## 4. Architecture and code map

**Repo:** fungjkTorn/torn-fren

**Production VM details previously provided by user:**
- SSH target: ubuntu@150.136.108.146
- Local Windows key path: C:\Users\fungb\Desktop\.ssh\torn-fren.key (path only; do not request, read, display or commit key bytes).
- Research checkout on VM: /home/ubuntu/torn-fren-v38-probe
- Research venv: /home/ubuntu/torn-fren-v38-probe/.venv/bin/python
- Current public web service: historically torn-fren-web.service at local port 8000; verify actual live state.
- Existing live collector DB: /opt/torn-fren/data/stock_history.db — READ ONLY for audits.
- Old V75 private predictions ledger: /var/lib/torn-fren-v38/v75_private_predictions.db
- New V128 shadow ledger: /var/lib/torn-fren-v38/v128_earliest24_shadow.db
- V128 shadow timer/service: torn-fren-v128-full24-shadow.timer and torn-fren-v128-full24-shadow.service
- Original V38 private timer: torn-fren-v38-private-shadow.timer
- Pinned private research stage: /home/ubuntu/torn-fren-private-models/v128_stage/pinned/research

Keep collector, timer and production files untouched until tested/authorized. Work's browser or computer access is NOT equivalent to verified VM SSH. Do not assume connected GitHub can read private VM paths. If Work cannot access VM, continue coding/testing in GitHub independently and keep the three read-only at-home commands queued.

**Very important deployed-source drift:**
- The research branch's web/static/ contains index.html and admin.html, not the actual experimental page's complete HTML.
- The research branch's web/app.py lacks the deployed /experimental and /api/experimental/v41/predictions routes.
- But deploy/scripts/v77_experimental21_source.sh and deploy/scripts/v87_web24_preview.sh explicitly verify those deployed routes. Historically 21 experimental entries used the V75 ledger; V87 provides opt-in 21+3 preview overlay (Panda/Lion/Japan Xanax). **It is UNKNOWN whether V87 is currently enabled or exactly what current deployed HTML looks like.**
- Never use git checkout, cp, rsync, or an app.py replacement to 'fix' the website until deployed sources have been read, compared, backed up and a guarded rollback exists.

## 5. Timeline and completed work — do not repeat

**Older specialist work:** V18–V20/V38, separate champion tournament winners for plushies/flowers. Country-specific specialist and Japan Xanax research are distinct from V128 generic challenger.

**V75:** older 21-item research private ledger powering prior experimental board. A limited historical targeted cohort had model selected 154/227 = 67.8% versus matched leave-now 169/227 = 74.4%, for Nessie/Red Fox subset context; do NOT generalize this to all 24 models or old V2.

**V87:** guarded three-item experimental overlay proposed to expand 21 to 24 with labeled unvalidated preview rows. Do not assume live enabled.

**V91/V97/V102–V127:** candidate decision policy, dashboard status semantics, restock+departure bridge, full replay/evidence framework, first-issue cohort, restock/depletion phases, real stock proxy and watch reconfirmation. Keep as reusable research, not a replacement product.

**V128:** all-24 private *experimental* earliest-credible departure simulator: 128 HIGH/LOW Monte Carlo trajectories, >=30 at arrival target, raw availability score threshold 0.60 at two consecutive five-minute bins, 8-hour grid, one row per item including abstentions. One five-minute batch of 24 records was confirmed on VM: issued_epoch 1791773040, captured_epoch 1791773077. **No verification that it continued running overnight.** Timer had been enabled; needs health check. Sidecar is separate from live web.

**V130:** phase-pinned Monte Carlo churn-reduction challenger committed/tested, NOT deployed.

**V129–V135:** frozen first-issue >=30 arrival proxy, older V75 and V128 comparisons, timing jitter/future WATCH reconfirmation (V132), private full-24 research display contract (V133), original V2 archived restock/cycle audit (V134), combined morning summary (V135).

**V137–V139:** deeper original V2 **direct >=30-at-arrival proxy** comparison with same-issue leave-now (V137), combined old/new morning audit (V138), safe one-shot pinned VM operator (V139). Source commit inside V139: 142f10363037b31fc299183c7cfb0734cf7df50c; operator file pinned at 112d574d9767912367fb8fcaf0870828f1de0e82. Their CI tests passed. The actual VM audit has NOT run.

**V140:** research/v140_existing_experimental_beta_board.py + tests/test_v140_existing_experimental_beta_board.py — PURE non-mounted adapter: exactly 24 item rows, preserved incumbent model plus separately labeled V128 challenger, statuses for stale/missing, graph deep links, refresh TTL, no invented GO/probabilities, no partial or mixed issuance V128 cohort. Does not deploy or create a duplicate HTML page.

**V141:** research/v141_v2_feasible_departure_window.py + tests — pure feasible-window guard; negative or collapsed proposed stock availability is NOT a departure. Nonzero stock now does not imply 30 at landing.

**V142:** deploy/scripts/v142_inspect_existing_experimental.sh + safety tests — read-only local HTTP probes of existing /experimental, / and experimental V41 API; prints count, unique keys, missing 24 roster keys, model/status/expiry fields, safe fingerprints, V87 drop-in presence, not secrets, not HTTP HTML body. Prepared for user's VM/Work if actual safe access exists; NOT yet run on VM.

**V143:** Research branch **web/app.py** and **web/static/index.html** have matching proposed V2 window collapse fixes, with tests/test_v143_v2_window_web_parity.py executing browser JS in Node and comparing to Python, including roll to P2 and clear stale P1. Research-branch candidate only; NOT deployed and may require reconciling live VM source divergence.

**Test verification**:
- Verified branch head c9091bd69e1225060eaddcc072d70f175b9c0990.
- GitHub Actions V85 isolation run 38284457908 SUCCESS, including V140, V141, V142, V143 and guarded syntax.
- GitHub V38 adapters, V35 pilot and profitability compatibility checks at same head all SUCCESS, per last check.
- None of these green synthetic/CI checks proves real Torn stock forecast performance or verifies the VM state.

## 6. NOT yet completed — accurate status of 24-item beta

### Already done
- Existing dual-view product clarified and documented.
- Individual specialist/incumbent roster preserved.
- Generic V128 recorder code and timer deployment procedure exist.
- Live graph candidate browser/server feasibility fix committed (research only).
- All-24 beta board compatibility adapter + tests and source drift inspection prepared.
- Old V2 vs V75 vs V128 audit scripts and comparison methodology committed.
- CI on last verified research head successful.

### Still blocked / not verified
1. **V128 private timer health/overnight repeat issue batches** after initial 24 predictions.
2. **Real forward-arrival stock proxy outcomes**, unknown/maturity accounting, original V2 accuracy, item-by-item results, matched leave-now baseline.
3. **Actual deployed /experimental page** contents, route implementation and installed V87 overlay. GitHub checkout cannot substitute for VM sources.
4. Exact champion source integrity and model selection per item (especially source_verified=false entries and preview-only).
5. Real-world usable time-to-leave accuracy, future WATCH reconfirmation, departure churn, per-country upstream feed freshness.
6. Integration of V140 into EXISTING deployed /experimental, not new page.
7. Integration of V143 into actual server/browser after drift reconciliation and guarded rollback.
8. Desktop/mobile functional tests, timers, stale/offline behavior, link to graph, 24 rows, country filters, and load under concurrent traffic.
9. Clear beta readiness/reporting criteria, item-by-item limitations, and explicit user go-ahead for any production changes.
10. Eventually scale to 200+ catalog items without expensive per-request live replays.

**Do not report all 24 models as beta complete, do not claim verified success percentages, and do not merge/deploy just because CI is green.**

## 7. USER'S THREE PENDING AT-HOME ACTIONS — PRESERVE EXACTLY

Source: docs/home_vm_actions_20261012.md. User said they are currently away from their PC. Previous missed V131 standalone and V135 older morning commands are SUPERSEDED by consolidated V139. No need to run them individually.

Open Windows PowerShell, then:

### Action 1. V128 and V38 timer health — observational only

~~~powershell
$key = "C:\Users\fungb\Desktop\.ssh\torn-fren.key"
$remote = "ubuntu@150.136.108.146"

& ssh -i $key $remote 'echo "===== TIMERS ====="; systemctl is-active torn-fren-v128-full24-shadow.timer; systemctl is-active torn-fren-v38-private-shadow.timer; echo "===== V128 LAST SERVICE ====="; systemctl show torn-fren-v128-full24-shadow.service -p Result -p ExecMainStatus -p ActiveState -p SubState --no-pager; echo "===== RECENT V128 RUNS ====="; journalctl -u torn-fren-v128-full24-shadow.service --since "12 hours ago" --no-pager -n 35'
~~~

The one-shot service can legitimately be inactive *between* timer firings; look at Result, ExecMainStatus, ticks and ledger, not ActiveState alone.

### Action 2. V139 consolidated retrospective and frozen forward audit — database read-only

~~~powershell
$auditLog = Join-Path $HOME "Desktop\torn-fren-v139-audit.txt"

& ssh -i $key $remote 'cd /home/ubuntu/torn-fren-v38-probe && git fetch origin research/v38-full-roster-live-prep-20261009 && git show 112d574d9767912367fb8fcaf0870828f1de0e82:deploy/scripts/v139_run_enhanced_departure_morning.sh | bash' 2>&1 | Tee-Object -FilePath $auditLog

Write-Host "Saved audit output to $auditLog"
~~~

This stages pinned *research Python files*, updates git fetch metadata and may compile into the private research staging area; it does NOT write collector or sidecar databases, modify the public website or restart services. Has prerequisites for collector/V75/V128 DB and venv; if missing, report failure rather than improvising operations. V139 combines V129, V131, V132, V134, V135, V137, V138 and related code.

### Action 3. V142 safe inspection of original deployed two-view site

~~~powershell
& ssh -i $key $remote 'cd /home/ubuntu/torn-fren-v38-probe && git show 4e4295c47a8a147c7f56f931080cf617f73692a1:deploy/scripts/v142_inspect_existing_experimental.sh | bash' 2>&1 | Tee-Object -FilePath (Join-Path $HOME "Desktop\torn-fren-v142-site-probe.txt")
~~~

Shows experimental/V2 routes, response counts, 24 keys, per-item model/status/timestamps, deployed web SHA256, existing HTML names, V87 flag. No secrets or HTTP bodies printed. If access fails, capture errors.

Send the next Work session the timer output plus files:
- Desktop\torn-fren-v139-audit.txt
- Desktop\torn-fren-v142-site-probe.txt

**Never paste API keys or SSH private key bytes.** A full giant SQLite DB is not needed for these steps.

## 8. PRIORITY WORK QUEUE FOR NEXT WORK SESSION

**Priority A — immediately, independently of user's PC:**
- Read this handoff and the four linked docs:
  - docs/v2_first_product_recenter_20261012.md
  - docs/existing_experimental_and_v2_beta_readiness_20261012.md
  - docs/home_vm_actions_20261012.md
  - docs/v139_recovered_continuation_handoff.md
- Verify current GitHub branch HEAD and Actions tests after handoff, keep isolation.
- Inspect existing experimental page deployment scripts (V77/V87), existing legacy API row schema, V140/V141/V143 contracts and V2 server/client tests.
- Audit functional mismatches or missing fields, implement incremental research-branch fixes with tests, verify JS+Python, improve input freshness/status/clock re-evaluation. Preserve incumbent labels and detailed graph links.
- Avoid duplicate experimental HTML; design feature-flagged integration into the deployed original after source inspection.
- Prepare robust read-only desktop/mobile acceptance tests or browser-based QA on the existing site if publicly accessible and user-authorized (avoid credential requests).
- Produce actionable per-item beta readiness matrix with statuses UNKNOWN where VM data hasn't been observed rather than invented model accuracy.
- Document exact safe rollout/rollback steps, with preflight hash checks. No rollout before live source reconciliation and explicit approval.

**Priority B — when VM evidence is available (via approved Work access or user runs above commands):**
- Check exact 24-item V128 issue batch repeat and scheduled cadence, run V139, categorize as-issued outcomes: matured success / miss / censored unknown / not issued / withdrawn / stale.
- Compare original V2 forecast restock timing and direct arrival>=30 proxy to V75/V128 on comparable cohorts.
- Investigate low performers, watch churn and missed opportunities. Improve the original V2 fields and the existing list departures, not an isolated offline metric.
- Confirm game/provider freshness gaps and design optional limited arrival observation if needed, without extra live game polling unapproved.
- Integrate the same forecast+freshness+expiry contract into both existing views.
- Beta test /experimental board and detailed / graph under user-approved canary; rollback on failure.

**Priority C — after the 24-item beta is credible:**
- Turn forecast snapshots into a Torn Travel Assistant day planner, evaluate candidates considering travel + return + waiting + profit per player-hour; never automate gameplay.
- Expand coverage to 200+ products via cached/lightweight model tiers and optimized DB reads; ensure page and VM remain responsive.

### Definition of progress for every future task
Report: (1) tangible user-visible V2 or experimental board improvement, (2) test or real-data evidence, (3) file/commit/CI reference, (4) remaining caveat and next step. If only a new experiment version was created without a product impact, rethink the task.

## 9. References and checks

Research branch:
https://github.com/fungjkTorn/torn-fren/tree/research/v38-full-roster-live-prep-20261009

Successful CI at pre-handoff head:
https://github.com/fungjkTorn/torn-fren/actions/runs/38284457908

Existing experimental beta readiness:
https://github.com/fungjkTorn/torn-fren/blob/research/v38-full-roster-live-prep-20261009/docs/existing_experimental_and_v2_beta_readiness_20261012.md

Product-first strategy:
https://github.com/fungjkTorn/torn-fren/blob/research/v38-full-roster-live-prep-20261009/docs/v2_first_product_recenter_20261012.md

Saved commands:
https://github.com/fungjkTorn/torn-fren/blob/research/v38-full-roster-live-prep-20261009/docs/home_vm_actions_20261012.md

Recovered last-night continuation:
https://github.com/fungjkTorn/torn-fren/blob/research/v38-full-roster-live-prep-20261009/docs/v139_recovered_continuation_handoff.md

### Final reminder
This is an **active engineering project**, not a request for a new outline. The next Work session should start implementing and testing safe improvements immediately using the repository, report concrete commits/results, and defer only genuinely VM-dependent evidence. Keep the two established interfaces, restore focus on accurate V2-style restock/departure forecasting, prove the 24-item beta rather than declare it, and then build the Travel Assistant as a consumer of that shared forecast engine.
