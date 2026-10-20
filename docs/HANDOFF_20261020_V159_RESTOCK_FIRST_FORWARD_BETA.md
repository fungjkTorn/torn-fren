# TORN-FREN — October 20, 2026 handoff: V159 evidence → restock-first, validated travel beta

**Prepared:** 2026-10-20, US/Eastern.  
**For:** New ChatGPT conversation in **TORN Projects**.  
**Public research repo:** https://github.com/fungjkTorn/torn-fren  
**Working branch:** `research/v38-full-roster-live-prep-20261009`  
**Private data/research workflow repo:** https://github.com/fungjkTorn/torn-fren-research-private (`main`).  
**Important:** Multiple project conversations have advanced this repository. At handoff preparation the public branch most recent observed commit was `454121087a167ea8eccd3e82e5dcef95cda9e126` (2026-10-20 23:02 UTC; recursive physical-restock projection). Private main most recent observed commit was `b284dc3c6a5ad205ba792a6db26707aa49f17959` (2026-10-20 23:06 UTC). **Refetch current heads before doing any work.** Old document SHAs/pins are records of what was tested, not guaranteed current branches.

## 0. INSTRUCTIONS TO THE NEXT ASSISTANT — START HERE

**The user's last substantive request:** “Do itg” in response to the recommendation to stop creating selectors and **implement the meaningful next phase**: validate and improve actual departure recommendations, using item-specific incumbents and independent/paired research challengers; score forward, as-issued restock and arrival results, then integrate winning predictions into existing product views without breaking them. The user then asked to **create this handoff and continue in a new chat**. No additional forward-integration coding was completed in that brief “Do itg” exchange in this particular conversation before the handoff request. Do **not** suggest the user repeat the request or merely offer another plan; take action in the new chat.

**Read these first, in this order:**

1. `docs/RECOVERY_AUDIT_20261020.md` in the public research branch — **the newest restock-first recovery direction and corrected evidence semantics**. Latest sections cover `research/restock_event_clock.py`, ordinal physical events and separate purchase-window modeling. Oct 20 work may be ahead of V159. Current state should be reconciled with private repo October 20 changes.
2. `docs/TORN_FREN_PRODUCT_MASTER_BLUEPRINT_20261013.md` — authoritative three-view product contract and flight/event separation.
3. This handoff (V151–V159 frozen comparison and next release gate).
4. `docs/WORK_MODE_MASTER_HANDOFF_20261013_LATEST.md` for deep historical appendix; **its beginning directs readers to the newer private** `docs/HANDOFF_20261014_COMPLETE_RESEARCH_AND_PRODUCT.md` (very long but crucial for operational private runner and product goals).
5. The private repo `docs/RECOVERY_AUDIT_OWNER_AND_BASELINE_20261020.md`, private October 20 commits/results, and public `docs/SHARED_DEPARTURE_INTEGRATION_20261016.md`, `docs/PER_ITEM_RELEASE_SELECTION_20261016.md`, `docs/FULL_ROSTER_SHADOW_20261017.md`, `docs/V160_BETA_ACTUAL_USAGE_FIX_20261013.md`. Do not re-run already completed audits or rebuild existing forward collection.

**Key behavioral instructions:** Work independently using connected GitHub and existing private GitHub Actions where possible; inspect code, implement fixes, run tests/CI, analyze real reports. Do not act as though work continues in the background. Do not ask for repeated owner VM commands if private historical data and runner already suffice. Do not invent availability, accuracy, a production deployment, or a running service from old status logs.

## 1. TRUE USER GOAL — FORECAST RESTOCK FIRST, THEN REACHABLE FLIGHT

The owner wants a practical Torn foreign-item travel decision platform initially for **24 verified items**, eventually ~200–236+ items:

- **Forecast every real upcoming physical restock** in chronological order, as well as quantity-specific stocked and depleted periods. A physical item restock is an actual `0→positive` event; **quantity ≥30 is separately the purchase/arrival availability target**, not the definition of a restock. A positive top-up must not be confused with a fresh physical-zero cycle.
- For each predicted restock, evaluate whether a flight **departing now or later** can land when **at least 30 units are expected** and availability continues through arrival **+10 seconds** (existing research policy). If the next predicted restock cannot be reached, KEEP it visible but evaluate the next restock, and then the next, until the **earliest defensible reachable** event yields a departure or all are unsupported. **Do not create a departure by waiting for an arbitrary countdown to hit zero.**
- Re-evaluate on an intended ~5-minute causal issue cadence, and sooner only when genuinely new stock evidence and computation justify it. Each recommendation needs issue/cutoff/source identity, actual route-specific flight duration, expected departure and arrival, uncertainty bounds, proposed wait, deadline/expiry, and clearly labeled stale/unknown/reconfirm/abstain cases. Never silently move a missed departure point forward.
- Different items have very different high-stock lifetimes, low-stock gaps, restock frequency, route duration, provider freshness and special models. **Do not make a global model swap merely because aggregate accuracy increases.** Japan Xanax is a separate narrow-stock specialist issue; weak plushies need dedicated forward experiments.
- **Keep all three product experiences** on one shared versioned event+departure contract:
  1. **Original V2 single-item graph** at `/`: rich actual-stock graph, predicted restocks, uncertainty/depletion windows, live source health, selected item, departure countdown and estimated arrival. Research must make V2 better, never replace or delete its graph.
  2. **Existing `/experimental` board**: multi-item opportunities, item/category/country filters, future restocks, earliest usable leave time and land time, watch/recheck status, scaling from 24 toward all supported items.
  3. **Travel Decisions**: item search/categories/watchlist, personalized travel lengths/thresholds eventually, later opt-in read-only Torn API linkage and alerts. No autonomous flights, buys or prohibited scraping.
- User aspirations included near/arrival+10s reliability around 90% on some items, but **no such live guarantee or overall performance is established**. First show source-quality, actionable coverage, unknowns, missed opportunities, timing error and matched stock-at-arrival success; then release item by item.

## 2. LATEST VERIFIED RESULT IN THIS CHAT: V159 FIXED-CUTOFF AUDIT — DO NOT REDO AS THE NEXT MODEL

Owner successfully executed the final **READ-ONLY** V159 audit, `SSH exit code: 0`, with frozen `ASOF_EPOCH=1791896383`, `DAYS=1`, `MC_BUDGET=96`, comprising **576 first-issued item/UTC-hour cohorts across 24 items**. Raw historical outcomes are *collector-observed stock ≥30 at the model's arrival*, **NOT verified player flights, real purchases, prospective live publication, or independent future restocks**. Source observations/eligibility can still change through later backfill: same cutoff is not necessarily byte-identical frozen source provenance.

### Model results at exactly this cutoff

| Historical evidence | Frozen result |
|---|---|
| Original V128 proposed | 210 / 576 |
| V145 capped Monte Carlo | 92 / 576 proposed; 60/81 known HIT (capped at 96 simulations overall) |
| V148 explicit-stock-window | 486 / 576 proposed; 300/402 known HIT = 74.6% |
| V151 **independent** | 486 / 576; **319/413 known HIT = 77.2%**, 30 pending, 43 unknown |
| V151 versus leave-now, matched | 404 pairs; **26 V151-only HIT vs 14 now-only HIT = +12** |
| V151 versus V148, matched | 382 pairs; **45 vs 31 = +14** |
| V151 immediate versus later | 378 NOW, 108 FUTURE; among 81 mature delayed cases, 26 model-only wins vs 14 leave-now-only losses |
| V151 **always paired completed LOW→HIGH** | 486/576 proposals, **337/420 known HIT = 80.2%**, 28 pending, 38 unknown |
| Paired V151 versus independent V151, matched | **409 mature pairs**, **17 paired-only HIT vs 4 independent-only HIT = +13** |
| Paired V151 versus leave-now | 410 pairs; **net +25** |
| V158 **flight-horizon prequential router** | 486 proposed; 72 chose paired, 414 independent; **322/415 known HIT = 77.6%** |
| V158 versus independent, matched | 412 mature pairs; **4 V158-only HIT vs 1 independent-only HIT = +3** |
| V156 correlation router / V157 first-cycle prequential router | Both selected independent throughout and delivered **zero improvement** |
| V151 first-next-restock timing | **351** fully bounded observations, **25.4-minute mean absolute timing error**, 64/163/243 within 1/5/15 minutes |
| Japan Xanax | **zero reachable departure proposals**; 21 issue checkpoints had maximum modeled arrival-stock support below the existing 0.60 gate. Do not lower the floor just to fill coverage. |

**Never compare raw 80.2% vs 77.2% as a perfectly matched improvement**: denominators differ. Head-to-head exclusive wins/losses and independent-episode checks matter more.

### V159 audit — finally FIXED and VERIFIED, not zero

The 576-cohort historical replay's V159 grouping now yields:

- **285 distinct as-issued source HIGH/LOW phase groups with scorable raw independent-versus-paired comparisons:** **17 groups favor paired, 4 favor independent.**
- **287 V158-scorable source-phase groups:** **4 groups favor V158, 1 group favors independent.**
- **13 raw paired-only winning issue comparisons missed by V158's selection**.
- As-issued phase groups reduce repeated-hour inflation; they do **NOT** automatically identify different *future landing restock events*, and do not certify independent game-flight success.

Per-item raw paired-only advantage/loss **by as-issued phase groups** at the frozen cutoff:
- Favor paired: **Argentina Monkey 4–0; Canada Wolverine 2–0; Mexico Jaguar 2–0; South Africa Lion 2–0; China Panda 2–0; UK Red Fox 2–0; Canada Crocus 1–0; UK Nessie 1–0**.
- Favor independent: **Switzerland Chamois 0–3**.
- Mixed: **Cayman Stingray 1–1**.
- Other items 0–0 (often variants agree, not proof that either is good).
- V158 actually selected paired for **UK Xanax (20 issues), Hawaii Orchid (15), Monkey (8), Chamois (8), Camel (4), Lion (4), Nessie (4), UK Red Fox (4), Wolverine (3), China Panda (2)**. It inexplicably bypassed promising Jaguar cases and suffered a Chamois loss. Selection was **not** proven a better model policy.

### Errors diagnosed and fixed during this conversation

1. Initial V159 audit displayed 0 groups despite hundreds of matched outcomes. In `research/v146_v145_same_issue_replay.py`, the record dictionary assigned V145 `issue_phase` and `issue_phase_onset`, then accidentally overwrote both with `None`. Fixed + AST duplicate-key regression test.
2. Still 0 groups because `research/v149_v146_compact_report.py` wrongly read episode evidence from its derived `source` summary instead of top-level `result["issue_phase_episode_audit"]`; substituted empty values. Fixed + nonzero per-item rendering and fail-closed denominator tests.
3. New reporter correctly displays 285/287 episode groups. All four public GitHub CI workflows passed after the tested fixes; the owner confirmed the final VM run succeeded. **Do not retry this audit without a new rationale.**
4. `research/v159_issue_phase_episode_audit.py` counts actual model used after a fallback, not merely paired selection intent.

Historical source reference: `docs/v159_issue_phase_episode_robustness_20261013.md` and `docs/v159_episode_report_root_cause_fix_20261013.md`. Existing replay runner: `deploy/scripts/v146_replay_v145_from_existing_stage.sh` (inner pin from last read was `afbac3d3b93203aafc5d905f80d7739aa9c52f69`; **not** a live deployment and not necessarily newest research).

## 3. WHAT WAS ACTUALLY BUILT (V151–V159), AND WHAT IT DOES *NOT* DO

- `research/v145_provider_continuous_phases.py`: reconstruct stock>=30/stock<30 periods and directly bounded HIGH/LOW windows with source continuity. Historical source-phase evidence, not a physical 0→positive event clock by itself.
- `research/v151_stable_earliest_departure.py`: stable-seeded whole-cycle Monte Carlo, eight-hour search and five-minute planning; optional **60-second departure grid** (same 0.60 simulated support floor, future checks five minutes apart). On 576-ish issue replays, one-minute mode moved ~90 departures earlier, produced no extra proposals, and achieved only a modest +3/+4 matched improvements in earlier windows; no production promotion.
- The V151 **`cycle_sampling="paired_complete"`** option preserves directly adjacent completed LOW→HIGH durations; must have >=3 bounded pairs or abstains. The default remains independent. Paired stock-at-arrival proxy may improve, but the restock-onset MAE can worsen; it does not warrant universal promotion.
- `research/v152_first_restock_timing_evidence.py` measured first-next-restock onset; original V151 error ~21–26 minutes over the inspected windows. This is a serious problem for narrow-stock arrivals.
- `research/v153_recent_completed_restock_baseline.py` tried recent 3/5/10/all periods; recent-history timing was usually worse overall. **Reject blanket recency selection.**
- `research/v156_item_cycle_profile_router.py` used complete pair rank correlation, stock/low duration, and flight-to-cycle regime; selected paired **0** times. Did not improve arrivals.
- `research/v157_prequential_stock_survival_router.py` trained on previous completed cycles and tested held-out first-cycle stock survival; selected paired **0** times. Did not improve arrivals.
- `research/v158_flight_horizon_router.py` tests paired versus independent on actual country flight+10 seconds and delayed offsets using chronologically prior fully bounded cycles; selected paired sometimes, with marginal head-to-head lift, still not a validated per-item champion.
- `research/v159_issue_phase_episode_audit.py` is **post-hoc evaluation grouping**, not a new predictor or production integration. Its fixed final outcome is given above.
- `research/v146_v145_same_issue_replay.py` and `research/v149_v146_compact_report.py` evaluate/output historical matched evidence. These must not be mistaken for a forward as-issued ledger.
- All these changes were **research branch only** in this thread; original deployed `/` graph and `/experimental` were not overwritten. Work on additive shared views elsewhere must be reconciled, not replaced.

## 4. CURRENT OCTOBER 20 PARALLEL WORK — NEWER THAN THE V159 METHOD

**THIS SECTION PREVENTS THE NEXT SESSION FROM DUPLICATING INFRASTRUCTURE OR OPTIMIZING AN OUTDATED OBJECTIVE.**

### Restock-first recovery (public branch, Oct 20)

- `docs/RECOVERY_AUDIT_20261020.md` documents owner's actual recovered raw/corrected evidence and the restock-first objective. `research/restock_event_clock.py` now explores physical-zero→positive event clocks using empirical, completed-interval median, prequential ridge and recursive next-event logic. It carries **all chronologically predicted restocks**; first plausible flight-reachable purchase period is separate from the next physical restock. Some Oct 20 work continues ahead of the older V159 series. Current source was updated near handoff; fetch latest revisions before changing it.
- `research/physical_restock_identity.py` explicitly counts physical 0→positive events and handles ordinal first-event labels without nearest-timestamp hindsight matching. `research/saved_timeline_audit.py` inspects archived V2 forecasts, provider-poll continuity and “moving target” departures. Do not conflate legacy normal-cycle events with physical microrestocks.
- Oct 20 original-V2 geometry correction: `services/v2_departure_window.py` and V2 `_make_prediction` were adjusted **in source only**, to assess the actual modeled stocked interval rather than treating a passed recommended point as the end of reachability. **Not deployed or proof of live accuracy.**
- V88/V137 arrival-truth correction scans intervening transitions rather than just poll endpoints; intermediate sellout/refill or provider changes make an arrival bracket **UNKNOWN** rather than certifying an invalid success. Historical older hit rates need rescoring under corrected evidence.
- The recovered owner journal had **7,560 entries** across 24 items; ~35 complete capture cycles and nine observed UTC-hour buckets in an earlier summary, and 35-cycle/24-item owner reports. Some frozen scorecards can look strong while near-term executable advice is absent for seven plushie specialists. The full raw owner journal is NOT automatically accessible to the restricted private runner.
- A separate Oct 20 historical issue replay examined 37 fixed five-minute starts on an inspected development window and identified large waits, postponements and nonactionable recommendations; this is NOT an independent validation cohort. See the public recovery audit and private `docs/RECOVERY_AUDIT_OWNER_AND_BASELINE_20261020.md`.
- **No evidence here that the new recursive event-first candidate has been deployed or improved live user departures.** Prioritize testing it and connecting validated recommendations to the actual views instead of creating another generic version.

### Existing forward infrastructure: do NOT reinvent

- `research/v160_prospective_v151_shadow.py` already provides **opt-in 24-item prospective, as-issued five-minute collection** for independent+paired V151 and stores immutable issues in a separate private SQLite ledger; `research/v161_prospective_v151_forward_report.py` and `deploy/scripts/v161_forward_24item_scorecard.py` score it. This was enabled/running at least at a verified Oct 13 checkpoint, but **CURRENT Oct 20 timer/service and ledger status has not been freshly checked in THIS CHAT**.
- `deploy/scripts/v160_private_beta_board.py` is an isolated localhost-only research dashboard. Its viewer fix distinguishes genuine `NO_MODEL_CANDIDATE`, fresh `FUTURE_WATCH`, stale issue, already expired departure and `RECENT_ISSUED_NOW_RECHECK`; do not display old NOW recommendations as actionable or silently set them to nonexistent. It is **NOT** the production `/experimental` page.
- `research/full_roster_specialist_shadow.py` and `research/shadow_scorecard.py` cover existing item specialists; `research.japan_xanax.renewal_shadow` provides a separate 24-item multi-variant private forward method. **Inspect existing journals, source/model SHAs, maturity and timers BEFORE starting a new recorder.**
- The restricted **private GitHub Actions** runner has already been set up for sanitized historical research; private `.github/workflows/forecast-research.yml` is configured for five-minute cron fallback / immediate approved-pin changes with expensive-input deduplication; sanitized dataset refresh was about 30 minutes as of Oct 14. Check current actual workflow state and approved SHA, **do not assume repeated cron executions refit models automatically**.
- The private repo `requests/approved_model_sha.txt` was observed as `a73adb6d786e0e7e710fcc99ec8c70e9e8319885` at handoff preparation, but verify before modifying. The private research runner intentionally cannot open owner live collector paths; do not weaken ACLs to work around that.
- `research/build_travel_event_snapshot.py`, `services/travel_decision_contract_v166.py`, `research/v2_beta_departure_bridge.py`, and `docs/SHARED_DEPARTURE_INTEGRATION_20261016.md` are existing **ADDITIVE staging work** for restock events + chosen departure read-model, Travel Decisions and original V2 graph; production `/experimental` source has been partially absent from the research checkout. **Never overwrite deployed `web/app.py` or `experimental.html` wholesale.** Confirm deployed hashes, routes and rollback before integration.
- Oct 18 country-clock metadata logging was **owner-activated** per `docs/COUNTRY_CLOCK_ACTIVATION_READY_20261018.md`; it yielded initial Japan receipts. It is not proof that the exporter/private runner already has country-clock training features, and does not by itself fix Japan forecast accuracy. Do NOT rerun owner activation on a host where installed.
- Private Oct 14 handoff contains broader V163/V165 restock research results. V163 event-window ±10m recall was around 47% on a 7-day fixed 4h test, with ±15s recall only ~2%; V165 event-conditioned at true flight lead is a hindsight-conditioned diagnostic, NOT an always-issued online success rate. Later Oct 20 clock research is distinct and must be compared on identical truthful event definitions.

## 5. NEXT DEVELOPMENT TASK — ACT, DON'T CREATE ANOTHER MODEL TOURNAMENT

**Immediate mission:** Finish a **coherent event-first forecast → feasible first departure → measured as-issued outcome pipeline**, using the latest public Oct 20 physical event-clock code **plus already existing** V160/live-specialist/private research infrastructure. The user explicitly wants real code progress toward the 24-item beta and the website, not many more isolated V-number reports.

Suggested implementation sequence (use real repo state rather than blindly following a superseded plan):

1. **Inventory current source and evidence.** Pull public/private heads and latest Oct 20 docs; inspect `research/restock_event_clock.py`, `research/physical_restock_identity.py`, `research/saved_timeline_audit.py`, `research/v160_prospective_v151_shadow.py`, V161 scorer, existing specialist shadow/scorecards, private Actions, live provider-clock evidence where permitted. Preserve existing capture ledgers. Check which Oct 20 report artifacts are actually complete; never claim VM access without an owner/connected action.
2. **Choose a frozen, causal event-first contract** shared by all candidate models: physical-restock ordinal forecasts with uncertainty; separately derive stock≥30 period and leave/land intervals given country flight+10s; first chronologically reachable event (or truthful abstention); earlier unreachable events retained in graph; source freshness and publication/expiry enforced. Validate input timestamps and prohibit future-data leakage. **Do not use future restock truth to choose a departure**; future is only for evaluation.
3. **Run matched historic evaluations via existing private runner and source evidence, not new VM data copy:** compare next physical event coverage/timing MAE ±15s/60s/10m, separate buy-stock survival ≥30 at landing+10s, earliest-departure timing, actionable coverage, average waits, missed first opportunity, failed/unknown/pending, stale/provider-invalid rates; match same issue/country/flight and true observed ordinal restock. Include leave-now and incumbent specialist controls plus V151 independent/paired where well-defined. Freeze score/evidence version and sample cohorts; no “best 80%” after changing denominators.
4. **Prospective validation:** extend/read V160 or existing full-roster model ledger **additively** with versioned event/departure fields as necessary, preserving old immutable rows and old models; capture every scheduled issue and all abstentions. If truly separate collector-required prospective run is necessary, obtain explicit owner permission for a nonconflicting sidecar and resource limits. Do not launch redundant live samplers. Evaluate by distinct physical restock and issued recommendation, not only hourly correlated proxy.
5. **Per-item promotion gate:** Existing proven V75/V2 specialist incumbents stay active. Paired V151 is a research candidate worth prospective testing on Monkey, Wolverine, Jaguar, Lion, Panda, Red Fox, and Nessie; **do not globally switch**. Chamois 0–3 clusters and Stingray mixed strongly caution against automatic paired. Japan Xanax stays on dedicated specialist/physical-zero modeling and needs credible very-narrow arrival support; don't lower arbitrary 0.60 floor to invent flights.
6. **Additive product integration:** Once a candidate passes genuinely frozen forward validation, use the versioned shared event/read-model to populate original V2 and the existing `/experimental` along with Travel Decisions, preserving all history graph, routes, user-facing semantics, last quantity and source freshness, countdown and uncertainty. Test with actual deployed source and rollback. No production deploy without explicit owner approval.
7. **Keep research resource bounded and timely.** The user explicitly rejected six-hour research feedback; private Actions can run when approved SHA changes and periodically, but snapshot freshness and VM CPU limits determine meaningful new evidence. CI passing is not model improvement. Prefer decisive targeted code/tests over another dozen model selectors.

**This is the correct pivot** from V156/V157/V158/V159 method selection to usable future-stock and departure recommendations.

## 6. SERVICE SAFETY, OPERATIONS AND COMPARISON PITFALLS

- Research V159 VM audit command used branch script `deploy/scripts/v146_replay_v145_from_existing_stage.sh`, which stages research scripts into a private model directory and executes a **read-only DB** replay under low CPU priority; user last run completed `SSH exit code 0`. It does write temporary staged source files, despite not writing production databases/services. **Do not rerun the same V159 report to manufacture further gains**.
- Public website originally on `/`, board `/experimental`, private V160 research viewer on localhost:8765, optional integrated three-view canary on localhost:8770. Private tunnel closure can hide pages even while VM runs; check service/route health before reinstalling anything.
- In PowerShell, start SSH command blocks with explicit `$key` and `$remote` initialization; previously undefined variables caused SSH to treat the command as the key path (`exit 255`). Do not store user's key or server address in public GitHub notes.
- Don't replace original `web/app.py` from a partial checkout. Don't touch collector, model services, enabled timers, private ledger, public websites, data permissions, or delete VM folders without explicit approval and a rollback plan. Do not describe any code commit as a VM deployment. V2 graph and experimental board **must remain intact**.
- Distinguish (a) physical zero→positive restock timing, (b) stock≥30 buy opportunity, (c) model-simulated support, (d) at-landing poll-state proxy with possible bracket unknowns, (e) real player flights, (f) actually actionable issued plans after publication/source expiry, and (g) distinct restock episodes versus repeated issued observations.
- Early evidence like archived V2 65.72% matched-stock vs 62.89% leave-now on 2439 cases, or V160/other seven-day analog reports, uses different endpoints/cohorts from V159; NEVER rank models by unpaired headline percentages. More recent October 20 `poll-state-v2-continuous-bracket` integrity correction can downgrade supposed known outcomes to UNKNOWN.
- Production physical restock collection, sanitized runner historical snapshots, private research prospective ledger and original V2 archive are **different sources** with different provenance, cutoff and access. Never silently merge or reuse outcome labels.
- Repo concurrent changes: check newest commit and modified paths, use compare-and-swap SHA for connector updates and CI recheck. If other chats are modifying the same research branch, coordinate via fresh pulls; avoid overwriting their current event-first clock or recent fixes.

## 7. HANDOFF ONE-PARAGRAPH BRIEF FOR THE NEXT CHAT

**Resume TORN-FREN now.** Read this October 20 handoff plus `docs/RECOVERY_AUDIT_20261020.md` and private Oct 14/20 context. Our frozen V159 audit succeeded after two evidence/report fixes: 576 item-hour issues, V151 independent 319/413, paired 337/420, 409 matched with 17 paired-only vs 4 independent-only wins; episode grouping 285 supported as-issued phases 17 favor paired/4 independent; V158 selector 72 paired choices/486 proposals with only +3 matched. These are historical proxy outcomes, not live player success. **The user already said “Do it”: implement useful forward, as-issued, event-first restock/departure advice; do not invent more global selector versions.** The repo already has V160+V161 prospective tools, existing item specialist shadows, private restricted ARM64 Actions and newer Oct 20 `restock_event_clock.py` / corrected V2 departure-geometry source. Verify current public/private heads and actual recorder freshness, then use existing research infrastructure to complete a causal restock→first reachable arrival contract with no-leakage tests and prospective forward scoring. Preserve all three views, original V2 graph and private services; do not deploy without owner approval.

## 8. FINAL HANDOFF CHECKPOINT — READY TO RESUME

**Finalized:** 2026-10-20. At verification, public research branch head was `6a2beb48ac0d4546dc55b16983c31c445eabe6a4` (this handoff's initial commit), and private research `main` head was `b284dc3c6a5ad205ba792a6db26707aa49f17959`. **This amendment creates a newer public head; refetch both heads before modifying code.** Confirmed by GitHub repository reads, not VM access.

**Do not treat V159 as the latest model or next task.** V159 is a historical audit and has been fixed/verified; the branch additionally contains October 20 physical-restock-first, ordinal-event and recursively later-reachable-drop research. The next developer should reconcile public `research/restock_event_clock.py`, `research/physical_restock_identity.py`, `research/saved_timeline_audit.py`, and private October 20 selected-drop findings, then **improve the shared event→flight recommendation pipeline** using the already existing forward recorders and specialists. The user last ordered: **“Do it”**—the implementation is the next action, not more handoff writing or another model-selection tournament.

**Known completed historical benchmark:** V159 read-only owner VM run finished with SSH exit 0 at fixed cutoff `1791896383`: 576 issued item-hours, independent V151 319/413 known HIT and fully-paired V151 337/420 known HIT; 409 directly matched, 17 paired-only versus 4 independent-only; 285 scorable source-phase groups (17 favor paired/4 favor independent); V158 chooses paired on 72/486 proposals, net +3 matched. Different denominators and source-phase groups **do not** establish prospective flight success, physical-event-recall or independently verified purchases.

**Implementation-first exit criteria for next conversation:**
1. Verify current source head and existing V160/V161/V75/private runner/physical event-clock state; do not create redundant instrumentation or reactivate working services.
2. Produce tested, causal, **ordinal physical 0→positive restock forecasts** and separately determine ≥30-stock-at-arrival windows. For each future event in chronological order, calculate actual flight and +10s landing buffer, select **first credible reachable event**; preserve all earlier unreachable restocks visibly. Do not wait for a countdown to reach zero to decide whether an already-impossible event is reachable.
3. Use immutable as-issued evidence, nonleaky forward scoring and independent physical-event grouping. Report missed restocks, extra predicted events, timing ±15s/±60s/±10min, arrival HIT/MISS/PENDING/UNKNOWN, wait/abstention and per-item comparison to incumbent, V151 and leave-now. Do not claim 90% unless genuinely established.
4. Present a concrete code diff, tests/CI and a source-pinned, reversible, **nonproduction** validation mechanism; if a VM or public deployment is necessary, ask for the narrow permission/step, never claim installed from GitHub alone.
5. Preserve all **three intended views** (original V2 graph, existing experimental all-item board, Travel Decisions) and user-facing specialist access. Avoid replacing partially missing deployed HTML or FastAPI routes from the public research checkout.

**Suggested first prompt to paste in a fresh TORN Projects conversation:**

> Continue TORN-FREN using `docs/HANDOFF_20261020_V159_RESTOCK_FIRST_FORWARD_BETA.md` on `research/v38-full-roster-live-prep-20261009`. Read `docs/RECOVERY_AUDIT_20261020.md`, `docs/TORN_FREN_PRODUCT_MASTER_BLUEPRINT_20261013.md`, and the current private Oct20 research/forward records. The final V159 episode audit is complete; do not repeat V151–V159 model tournaments. I already said “Do it”: inspect the latest physical-restock event clock and existing V160/V161 prospective tools, then implement and test actual chronological restock→earliest reachable departure logic with no future leakage, truthful ≥30 arrival/provenance, and item-specific incumbent comparisons. Work independently in GitHub, run tests, preserve the original V2 graph, experimental board and Travel Decisions, and make no public/VM production changes without my authorization.
