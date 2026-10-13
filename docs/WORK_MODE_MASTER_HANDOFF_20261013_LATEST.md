# TORN-FREN — COMPLETE MASTER HANDOFF (13 OCTOBER 2026)
> **OCT 13 LATEST V163 TESTED SOURCE / VM ACTION:** Expanded initial V163 event-level historical replay to report ±15s, ±60s and ±10m **all-observed-restock recall**, forecast precision and false forecasts, explicitly distinguishing fast Japan restocks from broad-window matches. Added live countdown for every predicted restock and player leave window in the *on-demand selected item* beta, not a scheduled V163 public 24-item predictor. Source `0bb7210532440faac4d1ec8a8fe3f4833effa3e9` passed V85 CI [38486340571](https://github.com/fungjkTorn/torn-fren/actions/runs/38486340571), plus initial other workflows; guarded viewer operator repinned at `4be871958055ddd06e9e5a1b915c4a8bd45176f6`. Follow ONLY [V163 setup and restock replay](V163_EVENT_FIRST_RESTOCK_BETA_20261013.md) for single VM command. Current VM still runs previous beta, V160 timer is still active; **NO actual V163 historical restock timing rates or true prospective V163 accuracy measured yet**. No claim of 90%. Separate restock-event forward capture/validations and dual-website rollout remain to be done.

> **OCT 13 V163 PRODUCT PIVOT — RESTOCK EVENTS FIRST, NOT ONE SCORED DEPARTURE:** User V162 REAL seven-day audit counted **182 Nessie**, **76 Japan Xanax**, **189 Jaguar** observed same-provider ≥30 threshold restocks, while V160 has only **79 new 5m batches** (~6h35). Nessie **77/79 V151 proposals** but V161 **3/4** evaluated first item/UTC-hour departure cohorts; not 4 restocks. Japan had **0/79 V151 departures** because all 79 both models returned `NO_TWO_BIN_SUPPORTED_DEPARTURE`, despite 76 confirmed historical restocks. The user correctly demands future restock **sequence** forecasts, next restock countdowns, flight arrival and leave-by windows, and **event-level** recall/timing (aspirational 90%, NOT achieved). Added RESEARCH-ONLY `deploy/scripts/v163_readonly_event_first_preview.py`: projects all modeled restocks in upcoming 8h (including ones player cannot reach), current phase-censored empirical restock and stocked duration, estimated time windows and appropriate flight geometry, no writes; explicit insufficient/overdue history abstention. Same CLI implements fixed 4h, nonoverlapping historical **causal as-of** replay scoring EVERY clean observed restock in window, one-to-one timing match ±10m, missed events, false predictions and precision/recall across 24 items. Historical event replay is **not genuinely forward 5m restock issue evidence** or guaranteed 90%. Updated selected-item `v160_single_item_recheck.py` to return V163 event list in the SAME pinned collector read-only snapshot as V151, and private beta UI to present every modeled restock with actual live countdown, unreachable restocks, first/latest estimated departure; cannot be presented as safely actionable when V151 abstains (especially Japan Xanax). Bounded, rollback-safe isolated private beta installer now stages V163 engine and preflights real current Jaguar event model before restart, leaving original V2, /experimental, collector and V160 issue ledger unchanged. All four CI workflows passed at source `a643dee513b6793bb2c01eb6538092722e5ed64d` including [V85 38485969404](https://github.com/fungjkTorn/torn-fren/actions/runs/38485969404). Pinned updater at `7a2f51c1a3a59f09badc6062a872f98bc557f628`. **User has NOT yet run V163 VM replay or installed V163 beta upgrade.** Detailed code, exact one-block PowerShell command, limitations and next 24-item accuracy benchmarks: [V163 event-first product handoff](V163_EVENT_FIRST_RESTOCK_BETA_20261013.md). Focus NEXT on actual historical event recall/timing results (Nessie, Japan), improve model, then prospectively freeze restock events every 5m and score on genuine later polls; never conflate V161 per-hour proposal hit rate with restock recall.

> **OCT 13 USER CORRECTLY QUESTIONS 'ONLY FOUR NESSIE RESTOCKS' AND JAPAN N/A:** The *V161 per-item scorecard* (user actual output) is Nessie independent=3/4=75%, paired=3/4=75%, `unique_issued_stock_phases=6`. **Neither denominator nor phases is a count of historical restocks.** V161 selected `first.setdefault((item,issued_epoch//3600),row)` — only first prospective model issuance per item per UTC hour, from the newly started V160 ledger, then counted only mature scoreable model proposals. `unique_issued_stock_phases` counts distinct `(phase,phase_onset)` identities in THOSE selected rows, not all completed collector restock transitions. Japan Xanax had 0/0 scored candidate arrivals, phases=4; this does NOT imply zero observed restocks. General V151 likely abstains under threshold; inspect real V160 every-five-minute `models.[independent|paired_complete].status` reasons and existing separate Japan specialist, never fabricate forecast hits. **NEW read-only historical audit:** `deploy/scripts/v162_readonly_restock_vs_forecast_audit.py`; uses change-only primary collector and private ledger read-only, exact 22+2 item roster, seven-day historical window, confirmed same-provider <30→≥30 threshold restocks, depletions, positive stock changes, ambiguous cross-provider thresholds and known collection gaps, plus actual per-item V160 issue/proposal counts. Prints especially Nessie restock counts and Japan reason histograms; does NOT backfill old predictions. One script command uses `git show <pin>:deploy/scripts/v162_readonly_restock_vs_forecast_audit.py | timeout 75s nice -n 19 .venv/bin/python - --days 7` in research VM checkout. Four GitHub CI workflows passed at commit `2c09c295c24f951992944ad33b2fd623f81b0a2c` including V85 [run 38484169599](https://github.com/fungjkTorn/torn-fren/actions/runs/38484169599). **Not executed on VM yet**, no live restock counts established. Next step user runs ONE read-only command and shares audit so we can determine if actual collector missed restocks vs forecast scorecard selecting few cohorts, and why Japan remains N/A. The user wants poll-backed accuracy, not required human flights. Preserve both original website views and active isolated V160 research recorder.

> **OCT 13 18:58 EDT IMPORTANT CORRECTION — NORMAL ZERO PHASES ARE NOT STALE:** The user correctly challenged the previous assistant's 10-minute per-item stale warning. Source inspection confirmed `research.v88_poll_state_forward_report` explicitly says `stock_history` stores **quantity/cost CHANGES ONLY**, whereas `poll_heartbeats` records each successful poll cycle. `research.v128_full24_earliest_shadow._read_item` uses stock-history deltas; `source_last_epoch` in V160 is the **last quantity-change timestamp**, NOT time since successful item polling. Thus Jaguar zero quantity with a last stock change 798 seconds earlier and global collector heartbeat 25s old is **normal, not automatically stale**. V88 forward scorer reconstructs carried-forward item stock at the successful polls bracketing predicted arrival (+10-second grace), checks absence of significant poll gaps, provider consistency and a permissive 24h max state age. This is appropriate empirical stock-at-arrival evidence for the project's goal without human flights; do not insist on gameplay verification, though distinguish sampled stock from guaranteed purchase. The previous research UI's `ITEM_REPORT_CAUTION_SECONDS=600` and `VERIFY STOCK FIRST` for merely old deltas was **WRONG** and has been reverted; relabels timestamp as *last quantity change* and trusts normal unchanged 0 between healthy poll cycles. Regression JS now proves 798-second last-change zero remains a legitimate forecast input. GitHub V85 [38481699041](https://github.com/fungjkTorn/torn-fren/actions/runs/38481699041) and all four CI workflows passed at `f2d091336b8e2b3b13b06cb0633c008e2a474ac5`. Repinned guarded private-viewer-only updater at `b5a629cb6a7ec3dd52d175dbf45be34763e6401f` (this later UI is **NOT YET installed on VM**; existing V160 recorder undisturbed). Also added `deploy/scripts/v161_forward_24item_scorecard.py`, a read-only 24-item per-key scorecard from existing V161 report JSON, with separate scoreable hits, misses, pending, abstentions and phase counts; tests passed. **Latest actual observed aggregate** from user: independent 45/61=73.8%, paired 45/62=72.6%; both cover 24-item roster but per-item hit rates cannot be inferred from aggregates alone. These are genuine as-issued forecasts scored against the successful poll brackets, not retrospective as-of backfills or actual player purchases. Prefer poll-backed hit-rate for evaluating target. The earlier handoff paragraph asserting Jaguar source is stale solely due to >10-minute stock delta is superseded and MUST NOT guide future code.

> **OCT 13 16:45 EDT — FIRST REAL V161 FORWARD STOCK PROXY RESULTS:** User successfully deployed the clearer private beta and ran V161 read-only report. VM printed `First-issued item/hour cohorts: 120`, `Recorded five-minute rows: 1104`; independent **45/61=73.8%** mature stock-at-arrival poll proxy, paired-complete **45/62=72.6%**, with **37 pending each** and 1 independent unknown. Direct paired-only wins **1**, independent-only wins **2**; **no proven model improvement or live flight validation**, no per-item champion promotion. Roughly five item-hour slots per roster item (120/24), and rows within/cross items/restock cycles are correlated; not a reliable per-item sample yet. Genuine prior issuance and later bracketed stock observations, not actual purchases. VM current one-item Jaguar recheck gave independent 39/48=81.25% and paired 46/48=95.83% scenario support; **these scenario fractions are not accuracy**. Critical source-quality finding: Jaguar `issued_epoch=1791924336`, `source_last_epoch=1791923538` -> item-specific last stock report **798 sec = 13m18s old** despite global heartbeat **25sec**; last reported stock **0**. A generic collector heartbeat cannot certify fresh item stock. Added read-only UI caution `ITEM_REPORT_CAUTION_SECONDS=600`, `VERIFY STOCK FIRST` for old/unknown item reports and no unqualified LEAVE NOW on an on-demand check with stale item data; preserved all prior model evidence and unchanged backend as-issued ledger. Tested actual JS behavior for 798-second Jaguar case and fresh item sample in GitHub [V85 CI 38465790031](https://github.com/fungjkTorn/torn-fren/actions/runs/38465790031), source commit `f80440e0fa8188cb81185f4a010701a911eccf7b`; repinned existing rollback-safe private beta updater at `3d03479e9270ecc6bca77c9855ca3d5e77997de5`. This is **research branch code, NOT automatically installed** on VM; currently running beta still previous UI until explicit private viewer-only opt-in upgrade. **Preserve original V2, /experimental, stock collector and active V160 timer; no winner yet.**

> **OCT 13 14:28 EDT — USER SCREENSHOT VALIDATES BETA UPGRADE; ACCURACY AND SIMPLE DECISIONS NEXT:** The user successfully upgraded the real private beta; VM installer printed `V160_BETA_HTTP_READY`, HTTP 200 after 3 retries, full 24-item ledger, and **one genuinely fresh Jaguar Plushie single-item recheck** (`issued_epoch=1791915309`, source heartbeat age 24s, both models `departure=issued_epoch`, scenario fractions 44/48=91.67% independent and 46/48=95.83% paired, stock last observed ZERO). **These scenario fractions are NOT validated probabilities or proof of stock on actual landing.** Browser screenshots show 7 upcoming, 14 recently-issued NOW indicators requiring recheck and 3 without a qualifying future window, 18 agreeing times within 5m — these are COVERAGE/AGREEMENT, NOT forward accuracy. Historical V159 proxy paired 337/420=80.2%, independent 319/413=77.2%, different eligible denominators, no real player flight proof. Current V161 genuine prospective success is still UNKNOWN without read-only report on mature later stock data. User said page is text-heavy/confusing and wants plain departure and ETA. **New research-only decision-first UI** `deploy/scripts/v160_private_beta_board.py` places clear earliest upcoming departure, expected arrival, flight length, ranked windows, direct one-click fresh item check, explicitly labels disagreement as `TIMES CONFLICT · RECHECK`, and puts all technical 24-row and simulation fractions into collapsed details. It preserves stale/expired warnings and never represents a 2-minute-old NOW signal as fresh. Four GitHub CI workflows passed at source commit `c88578f6b8a42e6baa17eee79aebabc25c230fbc`, especially [V85 run 38448060960](https://github.com/fungjkTorn/torn-fren/actions/runs/38448060960) with Node browser syntax, API, recheck authorization, and decision UI tests. The **existing fail-safe private viewer-only upgrade script**, `deploy/scripts/v160_beta_decision_and_recheck_upgrade.sh`, was repinned at commit `95c4414b32996f4f3a05b4f828bc12a81885f23c` and still retries 40s, verifies 24/24 API and rollback, source previews Jaguar BEFORE restart. **This new simpler UI is NOT YET INSTALLED on the VM**; old upgraded dashboard remains until user runs the pinned script. Both existing production V2 graph and `/experimental` plus independent five-minute V160 recorder remain untouched.

> **OCT 13 14:00 EDT ACTUAL VM UPGRADE FAILURE AND FIX:** The user executed `deploy/scripts/v160_beta_decision_and_recheck_upgrade.sh` and supplied `urllib.error.URLError: [Errno 111] Connection refused` after the new viewer restart, followed by `Restoring previous beta viewer only` and `FAILED new private page smoke; old private page restored.` The script's original post-restart HTTP check made ONE immediate request with ZERO retry; `systemctl restart` does not guarantee the service has already bound its socket. That definite installer defect plausibly caused the failure, but **a real Python service crash is not ruled out** because no VM journal was yet supplied. The original rollback script **did not verify** that the previous viewer was actually serving after restoring files. New research-only fix: `deploy/scripts/v160_beta_http_readiness.py` polls loopback up to 40s, checks real 24-row API + new UI, distinguishes permanent errors, and validates old-service rollback on failure. Upgrader now prints private service status/journal on failure, restores previous board+helper, and verifies rollback HTTP (25s), as well as diagnosing any already-inactive viewer before attempting replacement. Source CI on `58da25f27eedb444fdd3bc5251fd95253c963c48`: four workflows passed; V85 [38444124263](https://github.com/fungjkTorn/torn-fren/actions/runs/38444124263) includes deterministic refused-connection/retry tests, stale 503, incomplete 24 rows, real localhost old rollback. Updated safe installer is `deploy/scripts/v160_beta_decision_and_recheck_upgrade.sh` at commit `71e2aeccb868a8736cd3f91dffc23f20d06e6f0e` (still pinned to `58da25...`). **Do not claim current VM page is upgraded**; exact latest status still unknown, older viewer may or may not be running. Running V160 recorder, production collector and both existing V2/experimental web views were not targeted. Next: run ONLY corrected pinned opt-in private installer once in a fresh PowerShell; if it still fails, its included private unit journal/status explains the blocker, and old-page recovery will be checked rather than assumed.

> **LATEST USER-FACING BETA FIX — OCT 13:** The user provided screenshots of the REAL running private beta: 3/24 future-departure rows and most remaining rows falsely said `No departure · provisional scenario supported departure`. Root cause: as-issued V151 immediate departures were hidden after 30s but treated like abstentions. Research branch now fixes this with explicit `RECENT_ISSUED_NOW_RECHECK`, `FUTURE_WATCH`, `DUE_NOW`, `NO_MODEL_CANDIDATE`, `DEPARTURE_PASSED`, `STALE_RESEARCH_ISSUE` states, a decision-first board with upcoming opportunities and recent NOW indications, source observation age, and a dedicated **Recalculate this item NOW** control. The latter executes one current causal model prediction for a user-selected item, via pinned, read-only VM collector and isolated research stage; it never writes collector or V160 immutable forward ledger, so its interactive previews DO NOT inflate V161 forward evidence. 24-item snapshot, Node browser syntax, HTTP authorization, 20s throttling, zero-write and model-import tests passed on source commit `7e891f6325a948a11ba105f85b474328e6258460` in all four CI workflows; V85 research run [38441883871](https://github.com/fungjkTorn/torn-fren/actions/runs/38441883871). Opt-in guarded beta-only upgrade: `deploy/scripts/v160_beta_decision_and_recheck_upgrade.sh` at commit `7e891f6325a948a11ba105f85b474328e6258460` internally pins code `0225bb0b222a7b56cae5168f3102c5b8362fc7db`, preflights real V160 24 items and one Jaguar single-item recheck, backs up/restores prior private beta if smoke fails, restarts ONLY `torn-fren-v160-beta-board.service`. **This is code only: user has NOT yet run the beta upgrade; existing deployed page remains previous version.** It does NOT change the approved V160 recorder, original V2 graph or /experimental. See [actual-use screenshot bug and plan](V160_BETA_ACTUAL_USAGE_FIX_20261013.md). Until this VM upgrade is verified, do not claim on-demand recheck is live.


> **LIVE BETA INSTALL FIX — OCT 13, 13:22 EDT:** The user ran the earlier beta installer, which FAILED before installing the service with `ValueError: invalid 24-item roster` in `snapshot()`. Root cause verified: pinned `research/v38_roster.json` contains **22** canonical keys, and `research.v128_full24_earliest_shadow.exact_roster()` adds **Canada Xanax and UK Xanax** to yield the actual 24-key V160 ledger. The new beta reader incorrectly demanded 24 *in the raw JSON*. Fixed in `deploy/scripts/v160_private_beta_board.py`, which validates 22 canonical keys then adds precisely the two specialist keys; test fixture now copies real pinned `v38_roster.json` and derives the true 24 identities. All four CI workflows passed at source commit `e2898e65c40753059e1e75bb1a7fab5f952fb4a1` (including real-roster snapshot and HTTP tests); revised operator at `880be16b5f7f450132abcacd2c1049d371f49c67` pins that tested source. **The prior install failed before systemd enable; beta service is NOT yet verified installed/running. The already enabled V160 recorder was not modified by this failure.** Repeat one command with the updated operator pin as shown below. 

> **CURRENT PRODUCT IMPLEMENTATION STATUS — OCT 13, 2026:** To address the user's repeated complaint that research has not yielded a usable website, the research branch now contains a **real interactive, read-only V160 24-item private beta board**, `deploy/scripts/v160_private_beta_board.py`. The operator `deploy/scripts/v160_private_beta_operator.sh` safely installs a NEW optional localhost-only `torn-fren-v160-beta-board.service`, pinned to `e2898e65c40753059e1e75bb1a7fab5f952fb4a1`. It provides `/` and `/api/live` on VM port 8765 (127.0.0.1 ONLY) with 30s refresh, live countdowns, flight times, model comparisons and data-age guards; no DB writes, collector modifications, external game calls or changes to either existing website. 11 beta tests (8 HTTP/data, 3 service/operator) passed in [GitHub CI run 38436762128](https://github.com/fungjkTorn/torn-fren/actions/runs/38436762128) at operator revision `880be16b5f7f450132abcacd2c1049d371f49c67`. **VM beta service deployment has NOT yet been observed**; user must execute one complete PowerShell install+SSH tunnel block to open `http://127.0.0.1:8765/`. Exact code and steps: [V160 live beta access](V160_LIVE_BETA_ACCESS_20261013.md). Critical distinction: running V160 recorder has been verified; private UI not yet live in their browser; public `/` and `/experimental` remain untouched and require drift-aware additive integration. Prioritize actual first browser use over another model tournament.

> **LATEST VERIFIED LIVE RESEARCH STATUS — OCT 13, 2026:** The user explicitly approved enabling V160 and ran the pinned operator `22e45cb287937315b75a463ca4ef0277cae57205` using `enable`, followed by `status`. **Timer `torn-fren-v160-forward24.timer` is ENABLED and ACTIVE.** Repeated preview passed with 24/24 research rows, collector heartbeat age **4s**, latency **6s**, independent/paired **17 candidates each** (coverage, NOT success). The first genuinely as-issued, private `v160_v151_prospective24.db` batch at **2026-10-13 16:56:00 UTC, issued_epoch 1791910560**, had **24 of 24 immutable item rows**, captured at **1791910579**, `batch_complete=true`. Next timer occurrence displayed: 17:01 UTC. SQLite file exists at `/var/lib/torn-fren-v38/v160_v151_prospective24.db` (40K, mode 0600). No collector or website modifications reported. **V161 prospective stock-at-arrival accuracy remains NOT measured/verified until mature subsequent arrival observations**; no actual player flights were tracked. V160 is now RUNNING, so older handoff warnings that it is not installed are historical ONLY. Leave it operating, run read-only `status`/`report` later for actual maturity. `docs/v160_smoke_dependency_fix_20261013.md` records the first failed and corrected smoke attempts.

> **OCT 13 VERIFIED VM UPDATE — SUCCESSFUL V160 NO-WRITE SMOKE:** The user reran the corrected pinned operator and received `SMOKE PASS` with exit 0. Exact 24-item roster, `issued_epoch=1791910088`, 5-second capture latency, 27-second global heartbeat age, 15 independent and 15 paired proposals, `sidecar_written=false`, `collector_written=false`. The original missing V110/V38 schema stage dependencies are fixed. **V160 private timer remains NOT installed/enabled, no genuine forward issue has been recorded, and no empirical V161 forward accuracy exists.** The next step is explicit user approval before the isolated five-minute scheduled research recorder may be enabled. See [successful V160 smoke addendum](v160_smoke_dependency_fix_20261013.md).

> **UPDATED VM STATUS, Oct 13 (supersedes old pending language):** The user ran V160 status: `not-found`, `inactive`, zero timers, no prospective DB. The first smoke FAILED before forecasting because the staged bundle omitted `research.v110_multicycle_restock_horizon_audit`. A dependency-closure audit found also missing `research.v38_snapshot_schema`. GitHub research-only fixes are committed with isolated CI checks; the corrected operator is pinned at `22e45cb287937315b75a463ca4ef0277cae57205` and internally stages tested source `0164d64c0c94f045a9e6680054edc780738bcb63`. **V160 is still NOT enabled or producing verified forward issues.** Rerun ONLY the corrected `smoke` command below; do not enable or record without user approval. Details: [V160 smoke dependency incident](v160_smoke_dependency_fix_20261013.md).


**For:** Next ChatGPT conversation within the TORN Projects project, ideally Work mode for extended GitHub implementation.
**Repository:** https://github.com/fungjkTorn/torn-fren
**Active isolated branch:** research/v38-full-roster-live-prep-20261009
**Latest verified HEAD before this handoff:** cb2a25ede37d462cb2760e16dac74376c347a73e
**CI at that HEAD:** all four workflows SUCCESS (profitability VM private-canary compatibility, V35 museum/Japan private pilot, V38 expanded inference adapters, V85 Japan forward research).
**Earlier full architecture/product handoff:** docs/WORK_MODE_MASTER_HANDOFF_20261012.md. READ THAT TOO: this new handoff supplements and updates it.
**Final instruction before the user requested this handoff:** "Do it" — meaning: stop accumulating weak offline variants and begin genuinely forward, per-item validation and eventual dual-view integration. Do not ask them to repeat this instruction.

## 0. MUST READ: what the user wants, and what NOT to do

The goal is an actually usable foreign-stock **earliest departure** forecast for Torn. Given item, destination and its PI/pilot flight time, recommend the **earliest credible time to leave** with the objective that >=30 units are still available **when the player lands**. Prioritize realistically timed departures and accurate restock/depletion forecasts, not a misleading retrospective hit percentage.

PRESERVE BOTH established website experiences:
1. **Original Prediction V2 detailed stock graph, at /** — actual item stock history, multi-cycle projected restocks and sellouts, forecast uncertainty, arrival feasibility and time-to-leave countdown.
2. **Existing /experimental multi-item dashboard** and its API, where users compare all items, next opportunities, model identity, freshness, urgency, time-to-leave and links into V2.

Research was supposed to improve the existing V2 forecast, **not** replace the graph with an unrelated dashboard or tournament winner. The actual deployed experimental UI is NOT fully present in the GitHub research checkout. Never overwrite its deployed web/app.py or HTML without reading, diffing and fingerprinting the live source first. Keep incumbent specialty model champions, older research shadows and both website pages working.

Never run live game travel, purchases or any automated Torn gameplay. Never touch production collector database, website services, V75/V128 timers or production branches without explicit authorization and tested rollback. All recent changes have been on the research branch. User often works away from Windows/VM and wants autonomous GitHub development rather than repetitive commands and questions.

## 1. Most recent user direction: "Do it"

The preceding assistant had explicitly proposed:
- STOP adding V-numbers solely to report research results. Commit **actual useful model/website engineering**.
- Use per-item strategies because stocked lifetime, depletion/restock cadence, destination flight, confidence and feed freshness vary. Do not indiscriminately apply paired bootstrap to every item.
- Compare per-item **existing specialists**, generic V151 independent, generic V151 paired-complete, and optionally 1-minute departure granularity.
- **Start a GENUINELY prospective shadow**: freeze model recommendations when issued, every 5 minutes, then only later compare matured arrivals with provider stock evidence, same-issue leave-now and real near-issued V75 forecasts. Count pending/unknown honestly.
- Compare by distinct completed stock phases/events, not only repeated item/hour snapshots.
- Improve weak items individually (especially Japan Xanax), and integrate validated changes into the existing experimental UI and detailed V2 experience *additively* with feature flag, deployed-source reconciliation and rollback.
- Move toward a reliable complete 24-item beta, then 200+ items and a profit/time-aware Travel Assistant (recommendations, not automated gameplay).

IMPORTANT REPOSITORY UPDATE DISCOVERED WHEN THIS HANDOFF WAS PREPARED: **V160 prospective capture and V161 forward outcome/report code have ALREADY been implemented and tested on GitHub since the last V159 discussion.** The operator and five-minute isolated V160 systemd timer files are in the branch. Do not rebuild them from scratch. BUT **nothing in this conversation verifies V160 was installed, enabled, or recorded genuine VM forward snapshots**. GitHub CI and a file commit alone do not install services on the VM.

## 2. Fixed forecast and evaluation contract

- Exact initial roster of **24** item/country pairs; potential 200+ later.
- Recompute / replan **every five minutes**; a future WATCH departure must be re-confirmed near departure.
- Research V151 plans up to **8 hours** forward, default **300-second departure bins**. The optional 60-second grid was tested; it is not automatically the deployed default.
- Correct destination-specific outbound flight time (PI + pilot per scripts); threshold **>=30** at arrival, model checks **+10-second grace**.
- Existing modeled scenario-stock fraction threshold **0.60**, **UNCALIBRATED** and not a 60% real-world success probability. Future candidates require sustained forecast support five minutes apart; a supported NOW can qualify immediately.
- Replenishment onset, expected period of stocked availability, and candidate leave-at times are distinct fields. Getting restock timing right does NOT imply >=30 lasts until the aircraft lands.
- Evidence: ONLY predictions truly issued before the observed arrival. Compare same item/issue and mature, observable cases, never use future history in the feature window. HIT/MISS/PENDING/UNKNOWN/ABSTAIN/no proposal must be separate; missing poll brackets = UNKNOWN, not false failure or success.
- A global collector heartbeat does not establish each country/provider is fresh; model input/source age and provider provenance matter.
- Relevant metrics: source freshness, next-restock MAE, stocked/depleted duration uncertainty, departure coverage/abstention, matched >=30-at-landing poll-state proxy vs leave-now and incumbent, delays and WATCH reconfirmation, arrival uncertainty/unknowns, per-item performance and independent replenishment-episode replication.
- Historic hourly cohorts and even distinct as-issued phase groups are NOT independent verified future restocks or actual user flights. No user purchase guarantee from those retrospective proxies.
- No globally uniform model: typical plushies live stocked ~25–32min and depleted ~15–16min; many flowers stay stocked 3–5 hours and are depleted ~60min; Japan Xanax typically stocked ~12min and depleted ~120min in the latest 24h replay.

## 3. Exact 24-item roster and incumbent specialists (keep!)

| Country key | Item | Previously established incumbent or research family |
|---|---|---|
| arg | Ceibo Flower | V18 dyn3 |
| arg | Monkey Plushie | checkpoint4_online_selector / online_template_expert |
| can | Crocus | V18 dyn5 |
| can | Wolverine Plushie | V18 dyn8 |
| can | Xanax | V19 dyn8 |
| cay | Banana Orchid | V18 dyn7 |
| cay | Stingray Plushie | V18 dyn7 |
| chi | Panda Plushie | panda_pair_selector_ml / two_expert_extra_trees |
| chi | Peony | V20 traj12 |
| haw | Orchid | V18 dyn3 |
| jap | Cherry Blossom | V19 dyn2 |
| jap | Xanax | separately developed Japan Xanax specialist, not source-verified for this beta |
| mex | Dahlia | V18 dyn2 |
| mex | Jaguar Plushie | V18 dyn3 |
| sou | African Violet | V19 dyn7 |
| sou | Lion Plushie | lion_pair_selector_ml / two_expert_logistic |
| swi | Chamois Plushie | checkpoint4_online_selector / online_template_expert |
| swi | Edelweiss | V19 dyn9 |
| uae | Camel Plushie | camel_fast_selector / template_probability_selector |
| uae | Tribulus Omanense | V18 dyn3 |
| uni | Heather | V18 dyn3 |
| uni | Nessie Plushie | recent_phase_select / recent_phase_template |
| uni | Red Fox Plushie | rf_localgrid / global_regime_analog |
| uni | Xanax | V19 dyn3 |

Source: research/v38_roster.json (22) + two additional can:Xanax and uni:Xanax in research/v128_full24_earliest_shadow.py. Archived specialist implementations and helpers in research/plushie_champions/. V75 private specialist ledger historically covers 21 items. Some source_verified flags remain false/unknown. Do not invent live incumbent predictions for missing entries.

## 4. FINAL V159 fixed historical audit: accurate, fully grounded numbers

Latest user-supplied successful read-only replay was at immutable **REPLAY_ASOF_EPOCH=1791896383**, 1 day (24 items ×24 hourly issues) = **576 first-issued item-hour cohorts**; exit code **0**, collector DB, V128 sidecar and website unchanged.

- V128 original: **210/576** proposals.
- V145 corrected Monte Carlo: **92/576** capped proposals; **60/81=74.1%** of known mature; **411** otherwise eligible old/new cohorts unscored due to CPU cap. Never treat capped V145 coverage as full potential.
- V148 explicit stocked-window: **486/576=84.4%** proposals, **300/402=74.6%** known mature poll proxies; 42 pending, 42 unknown.
- **V151 independent**: **486/576=84.4%** proposals, **319/413=77.2%** known mature poll proxies, 30 pending, 43 unknown; 378 NOW /108 FUTURE.
- V151 vs same-issued leave-now: **404** matched, **26 V151-only wins /14 leave-now-only**, **net +12**.
- V151 vs V148: **382** matched, **45 V151-only wins /31 V148-only**, **net +14**.
- **V151 always paired LOW→HIGH**: 486 proposals, **337/420=80.2%** known mature, 28 pending, 38 unknown. On **409** directly matched mature independent-versus-paired comparisons: **17 paired-only wins /4 independent-only wins, net +13**. Vs leave-now 410 matched, net +25.
- **V159 correct phase grouping:** **285** distinct as-issued phase groups scorable in paired-vs-independent comparison, **17 phase groups favor paired, 4 favor independent**; V158-vs-independent **287** scorable phase groups, **4 favor V158, 1 favor independent**. There were **13 raw paired-only ISSUE wins V158 skipped**. This correct output follows fixes to overwritten phase-onset fields and incorrect reporter dictionary lookup.
- **V158 as-issued flight-horizon selector**: 486 proposals; **72 chose paired /414 independent**, **322/415=77.6%** mature proxies. Against independent V151: **412** matched mature, **4 exclusive wins /1 loss, net +3**. Vs leave-now 405 mature matched, net +15.
- V156 correlation router and V157 short-cycle prequential router both chose paired **0 times** and produced **0 improvement** vs independent; do not promote.
- Next fully bounded V151 replenishment-onset forecasting: **351** mature comparisons, **MAE 25.4min**, 64 within1min, 163 within5min, 243 within15min. Always-paired restock onset MAE ~**26.7min** on 351; improvement to arrival survival is NOT same as better restock onset prediction.
- Japan Xanax **zero** V151 proposals; 21 examined issues had peak simulated >=30-at-arrival support below .60. Its separate specialist research needs distinct forward validation, not arbitrarily lowering thresholds.

**Critical denominator warning:** 337/420 vs 319/413 use DIFFERENT mature sample denominators. Prefer matched 17-vs-4. Phase clusters are a more honest measure than hourly repetition but still not independent verified future restocks or flights.

### Item-level paired vs independent, distinct V159 phase groups favoring paired / independent
- Monkey Plushie **4/0**; Jaguar Plushie **2/0**; Wolverine Plushie **2/0**; Lion Plushie **2/0**; Red Fox Plushie **2/0**; Panda Plushie **2/0**; Nessie Plushie **1/0**; Crocus **1/0**.
- Chamois Plushie **0/3**, so paired is currently a negative candidate; Stingray **1/1**, mixed.
- Other 14 items: 0/0 exclusive grouped disagreements in this window, NOT validated ties or universal correctness.
- V158 paired selections on some: Monkey 8 hour-cohort recommendations net +2, Wolverine 3 net +1, Nessie 4 net +1; **Chamois 8 net −1**, and **Jaguar paired 0** despite raw paired apparent +2. Do not take these tiny outcomes as certified per-item champions.

## 5. Versions and features: what has been done, without needing another model tournament

Read the October 12 master for V18–V143 and detailed V2 deployment drift. Important recent milestones:
- V145: recover contiguous HIGH/LOW historical phase evidence across harmless provider switches; valid observed stock and depleted durations.
- V146: read-only same-issued historical replay with source guards and bounded CPU. V149: compact reporter for all 24 items and matched outcomes.
- V148 explicit-stock-window, V150 failure diagnostics.
- V151 reproducible Monte Carlo independent HIGH/LOW complete-cycle model, optional paired complete LOW→HIGH bootstrap and optional one-minute earliest departure scan; baseline default remains independent/5 minutes; models uncalibrated. Fine 1-minute scan historically ~90 earlier departures, net +3 to +4 matched versus coarse, no extra coverage — not a major fix.
- V152 quantified large first-next-restock onset errors; V153 recent-3/5/10 onset strategies often WORSE than V151; do not globally promote.
- V155 paired V151: item-specific apparent historical arrival gain, but Chamois harm.
- V156 rank-correlation per-item router: too conservative, zero selections.
- V157 chronological first-cycle Brier per-item router: zero selections, first-cycle target not close to flight decisions.
- V158 actual per-country flight-horizon heldout selector: selected paired in 72 fixed-cohort issues, but only +3 matched advantage.
- V159: distinct issue-time phase grouping. Corrected two real code defects: V146 duplicate dict fields overwritten phase/onset with None, and V149 reporter mistakenly used derived source instead of the top-level episode_audit. Latest V159 result above is VALID for issue-phase grouping. Regression tests now raise on missing/inconsistent episode evidence rather than print fake zeroes.
- **V160 NEW** (built since user's last V159 discussion): true immutable as-issued V151 independent/paired **prospective** private shadow capture, one read-only collector SQLite snapshot, full 24-item roster including abstentions, strict now-time issue bound, freshness, separate private sidecar ledger. Preview NO DB writes; recording explicit.
- **V161 NEW**: post-issuance forward scoring only for genuine recorded V160 recommendations, mature poll-bracketed arrival stock observations, same-issue leave-now, pending/unknown, stock age, future departure reconfirmation, and actual V75 specialist near-issued ledger proposals where valid (within 180s prior, still valid, matching source age). V75 roster label alone never counts as a specialist prediction.

**DO NOT start V162 or another generic selector just to fill a report.** Immediately focus on VM smoke, trustworthy forward evidence and then real integration.

## 6. GitHub/VM locations and DEEP deployment safety caveat

**Repo:** fungjkTorn/torn-fren.
**Branch:** research/v38-full-roster-live-prep-20261009.
**Pre-handoff latest branch SHA:** cb2a25ede37d462cb2760e16dac74376c347a73e (branch advances when THIS handoff is committed).
**Green CI at that SHA:** https://github.com/fungjkTorn/torn-fren/actions/runs/38425817796 ; https://github.com/fungjkTorn/torn-fren/actions/runs/38425817795 ; https://github.com/fungjkTorn/torn-fren/actions/runs/38425808344 ; https://github.com/fungjkTorn/torn-fren/actions/runs/38425808234.

**VM connection** (path only, NEVER share private key contents):
- ubuntu@150.136.108.146
- Win key path: C:\Users\fungb\Desktop\.ssh\torn-fren.key
- Git research checkout: /home/ubuntu/torn-fren-v38-probe
- Python venv: /home/ubuntu/torn-fren-v38-probe/.venv/bin/python
- Production collector DB READ ONLY: /opt/torn-fren/data/stock_history.db
- V75 ledger: /var/lib/torn-fren-v38/v75_private_predictions.db
- V128 private sidecar: /var/lib/torn-fren-v38/v128_earliest24_shadow.db
- V160 **NEW private sidecar only with user-approved opt-in:** /var/lib/torn-fren-v38/v160_v151_prospective24.db
- V146 read-only research staging: /home/ubuntu/torn-fren-private-models/v128_stage/pinned/research
- V160 isolated staged code: /home/ubuntu/torn-fren-private-models/v160_stage/pinned
- V160 service/timer: torn-fren-v160-forward24.service and torn-fren-v160-forward24.timer, separate from all old services.
- Existing V128 timer torn-fren-v128-full24-shadow.timer and V38 private shadow torn-fren-v38-private-shadow.timer; V75 collector/private ledger and public web must remain intact.

### Deployed original website source is NOT the research checkout
The branch's web/static/index.html and web/app.py do not include the deployed experimental page/API implementation. The VM historically provided / and /experimental plus /api/experimental/v41/predictions. V77 scripts describe prior 21-item page and V87 opt-in 21+3 preview overlay; actual current deployed V87 state is UNVERIFIED. FIRST run safe V142 site inspection (docs/home_vm_actions_20261012.md), inspect/hash/back up deployed app/HTML, then design a reversible additive integration. Do not copy research web/app.py or HTML into /opt or restart service simply because CI is green. V140/V141/V143 code for stock-window feasibility and 24-row adaptation is in RESEARCH only.

## 7. V160/V161 FORWARD SHADOW: coded, TESTED, NOT verified enabled

Files committed:
- research/v160_prospective_v151_shadow.py
- research/v161_prospective_v151_forward_report.py
- deploy/scripts/v160_forward_shadow_launcher.py
- deploy/scripts/v160_forward24_operator.sh
- deploy/systemd/torn-fren-v160-forward24.service, deploy/systemd/torn-fren-v160-forward24.timer
- docs/v160_v161_prospective_24_item_forward_study_20261013.md
- Corresponding research/VM/operator unit safety tests.

V160 defaults to **48** simulations per independent and paired V151 variant, with 105s program budget. Immutable issue rows carry true issue time, phase/source age, both model outputs or abstention, and item/source metadata. V161 reports last 2 days by default; reads V160 actual private issues and collector poll brackets AFTER maturity and optionally V75 true specialist near-issued valid candidates. These are **prospective research stock proxies**, NOT confirmed player purchases.

The V160 operator supports: **status** (observational), **smoke** (stage pinned research and preview no DB write), **record** (explicit one-off private issue), **enable** (smoke THEN install/enable only NEW isolated five-minute V160 timer), **report** (read-only V161 outcome summary), **disable** (disable only V160 timer).

Service guard rails: 5-minute calendar, Nice=19, CPU quota 30%, MemoryMax=512M, timeout 150s, PrivateNetwork=yes, ProtectSystem=strict, read-only collector data, private ledger write directory. It does NOT install itself from a GitHub commit. **Nothing in this conversation confirms status/smoke/record/enable/report ran on the VM.** Do not infer it is active; check.

Current operator was fixed at branch prehandoff SHA **cb2a25...** to accept a legitimate Git linked-worktree **.git file** using git rev-parse rather than requiring a .git directory. The operator itself pins a tested research source bundle at **510ea2fd2d6cfe3f124493a786cd1ef338c5995b**. The V160 docs contain an older operator example pin; use the linked-worktree-safe latest code instead.

**Read-only / NO-DATABASE-WRITE smoke command**, PowerShell with all variables initialized:

~~~powershell
$key = "C:\Users\fungb\Desktop\.ssh\torn-fren.key"
$remote = "ubuntu@150.136.108.146"
if (-not (Test-Path -LiteralPath $key)) { throw "SSH key missing: $key" }
$branch = "research/v38-full-roster-live-prep-20261009"
$pin = "22e45cb287937315b75a463ca4ef0277cae57205"
$script = "deploy/scripts/v160_forward24_operator.sh"
$cmd = "cd /home/ubuntu/torn-fren-v38-probe && git fetch -q origin $branch && git show " + $pin + ":" + $script + " | bash -s -- smoke"
& ssh -i "$key" "$remote" "$cmd"
Write-Host "SSH exit code: $LASTEXITCODE"
~~~

To inspect without staging anything, use the SAME pinned operator with **status**. After a successful smoke and **explicit user approval** for starting scheduled private writes/systemd, use **enable**. For subsequent mature forward outcomes use **report**; **disable** only affects the V160 timer. Smoke stages Python files and may create temporary/compiled research files; NO WRITE refers to the collector, public website and sidecar DB, not every VM filesystem path.

## 8. Prior frozen retrospective and pending VM checks

Pinned historical replay:
- deploy/scripts/v146_replay_v145_from_existing_stage.sh
- Internal research PIN afbac3d3b93203aafc5d905f80d7739aa9c52f69
- Historical cutoff **REPLAY_ASOF_EPOCH=1791896383**, 1 day, gives comparable 576 cohorts.
- Last run completed with "===== V146 REPLAY DONE; NO COLLECTOR, SIDECAR OR WEBSITE CHANGES =====" and SSH 0.
- This historical replay is finished as a *baseline*. DO NOT use repeated replay as a substitute for actual forward V160 issuance.

The earlier 12 October master listed three at-home actions whose completion is NOT confirmed in the current transcript:
1. V128/V38 timer health inspection (observational).
2. V139 enhanced original-V2 vs V75/V128 retrospective/frozen morning audit, if still needed.
3. V142 **safe deployed V2 + experimental source and route inspection** — must precede web modifications.

Exact scripts and self-contained commands in docs/home_vm_actions_20261012.md. Do not ask the user to re-run already provided V159 replay for no reason. Once V160 is active, prioritize forward evidence instead.

## 9. PRIORITIZED next engineering work — DO THIS, not another detached tournament

**A. GitHub now (no PC required):** Verify latest branch HEAD + four CI runs. Read this handoff, October 12 master and V160/V161 docs. Inspect V160/V161 frozen issue writes, provenance guards, V75 near-issued alignment, tests and operator; fix defects on research branch and run CI. Build a 24-item readiness view showing incumbent, independent/paired V151, retrospective signals, forward evidence count, confidence/abstention and status UNKNOWN where live source isn't verified. Report actual code/commit/test work, not vague study.

**B. VM observation & no-write smoke:** With authorized access, run V160 "status", then one "smoke". Verify 24 keys, timely source heartbeat, issue lag, CPU/memory, no sidecar writes, model abstentions/fail-closed behavior. The user is on Windows and sometimes PowerShell variables vanish; ALWAYS give complete commands including SSH key and host. Do not claim already deployed or enabled.

**C. Explicit user-approved isolated five-minute forward study:** After smoke, use V160 operator "enable" if user approves a new isolated low-priority timer writing only new private ledger. Check service/timer healthy, full 24 per issue, repeat five-minute issuance, no collision with existing V128/V38/V75, append-only unique issuance and no production changes.

**D. Evaluate actual matured V161 results:** Need several distinct completed stock/depletion/restock cycles and true future arrivals. Measure mature matched paired-vs-independent, leave-now, actual near-issued V75 forecasts, short/long departure waits, missed useful leave windows, issue churn, stock >=30 bracket quality and UNKNOWN censoring. Group by actual distinct restock episodes as well as issue-phase anchors. Do NOT turn zero proposals for Japan Xanax into fabricated errors.

**E. Choose per-item champion ONLY if supported prospectively:** Some retrospectively promising items: Monkey, Jaguar, Wolverine, Lion, Panda, Red Fox, Nessie, Crocus; Chamois paired was worse. No proof they outperform their actual incumbent specialists yet. Preserve incumbents or research fallback where insufficient samples. If V151 paired improves arrival but next-restock onset MAE is worse, reconcile these separate objectives and user-facing time-to-leave.

**F. Integrate real player-facing functionality after source inspection/approval:** Investigate actual deployed page and V2 graph via V142; preserve both existing UI views, charts, APIs and V75 champions. Shared typed contract: item, provenance, last verified stock, source last as-of, status/staleness, model identity/version, next restock band, >=30-at-landing forecast, earliest departure, forecast expiry/refresh, caution about simulations and fallback. Implement source-pinned additive flags, compare deployed checksums, create restore package, test browser+server, enable canary, rollback on failure. No duplicate /experimental HTML.

**G. Later:** 24-item beta with credible forward evidence; 200+ catalog items with lightweight cached forecasting tiers, no on-request 200 full simulations, bounded VM CPU and data retention. Then Torn Travel Assistant trip/day optimizer: outbound/return flight and waiting, expected stock, quantity, per-unit profit, profit-per-player-hour and schedule planning (not automatic gameplay).

## 10. Key files / links / source of truth

Original architecture and older jobs: docs/WORK_MODE_MASTER_HANDOFF_20261012.md.
Existing dual UI notes: docs/v2_first_product_recenter_20261012.md, docs/existing_experimental_and_v2_beta_readiness_20261012.md.
Actual existing VM commands: docs/home_vm_actions_20261012.md.
V151 independent/paired: research/v151_stable_earliest_departure.py.
V145: research/v145_provider_continuous_phases.py.
Frozen replay/reporter: research/v146_v145_same_issue_replay.py, research/v149_v146_compact_report.py.
V158: research/v158_flight_horizon_router.py.
V159: research/v159_issue_phase_episode_audit.py.
V159 bug details: docs/v159_episode_report_root_cause_fix_20261013.md and docs/v159_issue_phase_episode_robustness_20261013.md.
Current forward research: research/v160_prospective_v151_shadow.py, research/v161_prospective_v151_forward_report.py.
Forward manual VM operator: deploy/scripts/v160_forward24_operator.sh.
Forward stage launcher: deploy/scripts/v160_forward_shadow_launcher.py.
Forward systemd: deploy/systemd/torn-fren-v160-forward24.service and .timer.
V160 docs: docs/v160_v161_prospective_24_item_forward_study_20261013.md.
Research branch: https://github.com/fungjkTorn/torn-fren/tree/research/v38-full-roster-live-prep-20261009.

## 11. Opening prompt to paste into the new chat

Continue my TORN-FREN project. Read docs/WORK_MODE_MASTER_HANDOFF_20261013_LATEST.md and docs/WORK_MODE_MASTER_HANDOFF_20261012.md COMPLETELY on the research branch research/v38-full-roster-live-prep-20261009. Our final V159 as-issued phase-clustered retrospective (fixed cutoff 1791896383) showed 17 distinct paired-only wins vs 4 independent-only losses, but this is NOT real player-flight proof. V160 immutable prospective 24-item V151 independent/paired shadow and V161 forward outcome/scorer, plus guarded isolated five-minute VM operator, are ALREADY coded and green in GitHub, but NOT confirmed installed/active on the VM. Focus NOW on safe V160 smoke, true forward evidence and valid real V75 incumbent comparisons; improve model/website code, then plan guarded, reversible additive integration into BOTH existing original detailed Prediction V2 graph and /experimental dashboard. Never replace the deployed pages or incumbent specialists; do not create more generic research models just to get prettier reports. Work independently in GitHub/tests as far as possible; ask only for necessary complete VM commands; no production rollout without my approval.

## 12. Final status: progress versus undone work

DONE (research/code): 24-item definitions; V145 history continuity; V146/V149 frozen replay; V151 independent/paired/fine departures; true V159 issue-phase grouped historical evidence; V158 flight-horizon item selector; isolated V160 prospective forward capture and V161 genuine issuance-based report code; V160 safe operator/systemd bundle; green CI.

NOT DONE / NOT VERIFIED: V160 on VM (status/smoke/enable/private DB), any genuine V160 forward accuracy measurements, champion decisions against real incumbent specialists, reliable Japan Xanax supported arrivals, user-visible integration with existing detailed V2 and experimental board, exact deployed live source drift inspection, 24-item operational beta, 200+ catalog scaling or trip-profit planner.

The next session MUST treat this as an active engineering project and move toward substantive user-visible completion, **not restart basic retrospective diagnosis or overclaim historical percentages**.


## 13. Post-handoff reconciliation — read before asking for repeat VM work

**IMPORTANT: newer evidence supersedes older pending wording.** The prior October 12 conversation already reported V142 live-site checks (HTTP 200 for both views; existing experimental API 24/24, no missing/duplicate items, V87 installed), several V128 24-row batches with a transient failure/recovery, and completion of V139's historical audit. These point-in-time facts are NOT proof of current deployed source or recent V160 forward evidence. The previous conversation also discussed deployed-source copies, but do not assume they reside in the GitHub research checkout.

A safe research-branch update to V161 after this handoff separated PENDING/UNKNOWN/MISS, not-yet-due WATCH reconfirmation, and 24-item readiness with incumbent provenance. Current VM operator still needs a verified pinned source revision and the opt-in smoke steps; **V160 remains unverified on the VM, and no production rollout was approved**.

Read **[the Oct 13 reconciliation and forward readiness addendum](OCT13_HANDOFF_RECONCILIATION_AND_FORWARD_READINESS.md)** before following the older V139/V142 at-home action list or claiming the historical checks never happened.

**Updated operator pin for new smoke sessions:** the PowerShell `smoke` example above now selects the linked-worktree-safe operator at `22e45cb287937315b75a463ca4ef0277cae57205`, which internally pins verified source `da6db7cee81588b38cb8ee522be611ad7e173bda`. This supersedes the original `cb2a25...` smoke command, not the historical pre-handoff SHA record. DO NOT enable timers unless explicitly approved.

**Operator read-only status improvement (Oct 13):** this newest pinned operator inspects the actual sidecar (if present) using SQLite `mode=ro`, returning the latest three issue epochs and counts, whether each has all 24 item rows, and issue age. The uninstalled status is not equivalent to evidence of a live 5-minute V160 study. Only user approval can authorize the separate `enable` action.

**Latest pinned V160 smoke package (Oct 13 corrective follow-up):** operator `22e45cb287937315b75a463ca4ef0277cae57205`, source `0164d64c0c94f045a9e6680054edc780738bcb63`. Four GitHub CI workflows succeeded at the source commit, including a real isolated-stage import regression. Initial VM smoke failure is documented in `docs/v160_smoke_dependency_fix_20261013.md`. The old assertion that V160 status/smoke were never run is superseded by the observed failed run; the final successful VM smoke has not yet happened. No timer or sidecar was installed.
