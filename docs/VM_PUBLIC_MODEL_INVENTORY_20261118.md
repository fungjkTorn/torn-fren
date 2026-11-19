# Public prediction model inventory — 2026-11-18

**Checkpoint.** The final-pair production repair and rollout are on hold pending an explicit decision about Canada Xanax and Swiss Chamois. This read-only follow-up matched the 24 public rows to four publisher snapshots. It found scope-limited approval records for 11 assignments as deployed and left 13 with approval unknown at the exact policy level. Preserve the installed services, historical data, ledgers, and research collection while the owner reviews the inventory.

This follows the [VM service audit](VM_SERVICE_AUDIT_20261118.md). At 7:50 p.m. EST, verified SSH reads of the four local snapshots and a TLS-verified GET through the live Nginx route agreed on the 10 + 6 + 6 + 2 roster. Three cohorts were fresh and both final-pair rows were stale. Follow-up reads checked item policy markers, deployed entry points, and Canada country clocks. The audit ran no model inference and made no VM changes.

## Approval standard

- **Confirmed approved.** An explicit release record names the model assignment and scope. The scopes here are the ten-item live beta and the original labelled challenger forward test. The approvals do not extend automatically to later variants or certify accuracy.
- **Explicitly experimental.** An exact variant has an explicit research or experimental record for its role. The out-of-roster Japan example below meets this standard.
- **Approval unknown.** The records checked do not establish approval for the exact deployed policy in its current role. An original timing config can have approval while a later stock or timing policy has validation only. Unknown does not establish rejection.

The four model and publisher SHAs identify the snapshot's release lineage. The deployed November 14 policies show that code can change in place while those SHAs stay the same. The inventory therefore records runtime policy markers and source overrides alongside the timing configurations. `LIVE_BETA`, installed units, scores, and a code merge describe other facts and do not establish owner approval.

## Public outputs and versioned services

All four JSON files feed `/api/first-release`, which supports `/experimental` Hot List and All Items, the graph overlays, and the shared travel backend. The Beanstalk Hot List API combines the same board with the catalog. The publishers record evidence as well as serving public rows. Final-pair still occupies a public lane, with its stale advice suppressed.

| Lane | Service and website input | Reported model SHA | Reported publisher SHA |
| --- | --- | --- | --- |
| A — first ten | `torn-fren-first-ten-beta.service`, external reporting wrapper and pinned release → `latest.json` | `45d14b5e931458e41dc31e551310994caf4f8a1d` | `2fa6365859ec0ac8d160ac3d0ac9c5b43a90b56a` |
| B — challengers | `torn-fren-challengers-beta.service`, versioned `services.challenger_live` → `challengers/latest.json` | `8a8284d019272030e385bf5fb1b3cf5d4c8384a4` | Same as model SHA |
| C — next six | `torn-fren-next-six-beta.service`, versioned `services.next_six_live` → `next-six/latest.json` | `1781fb8318f9cd943063233b7c2d1eb339b0a5f5` | Same as model SHA |
| D — final pair | `torn-fren-final-pair-beta.service`, bounded-reader drop-in and external `final_pair_entry.py` → versioned `services.final_pair_live` → `final-pair/latest.json` | `6e3a5ed175cbe39ff3f7fa99b9b97c15e45a3ec8` | Same as model SHA |

Paths are relative to the live beta state directory. The running web configuration explicitly selects the first-ten file. The other lanes use the bridge's per-cohort defaults. The stock graph and the per-cohort website history summaries have separate historical inputs and can keep serving observations when the advice expires.

## All 24 public rows

R is the observed `REVIEWED_STOCKED_SAMPLES_AND_PHASE_GUARDS_20261114_V1` policy. R rows also reported `REVIEWED_FOUNDATION_20261111_V1`. B and C use full causal history, with C also selecting the reachable-current-stock branch. D uses `CORRECTED_CHALLENGERS_FIRST_REACHABLE_V1` and reports full-causal-history training. The listed timing assignment can abstain, yield to an event estimate, or be bypassed by a current-stock decision. The lane table identifies the service and output consumed for each item.

| Item | Lane | Deployed model and policy | Runtime role | Record | Status for deployed policy |
| --- | --- | --- | --- | --- | --- |
| `arg:Ceibo Flower` | A | `V18 dyn3` | Public advice when supported, plus evidence. | A | **Confirmed approved** |
| `can:Crocus` | A | `V18 dyn5` | Public advice when supported, plus evidence. | A | **Confirmed approved** |
| `cay:Banana Orchid` | A | `V18 dyn7` | Public advice when supported, plus evidence. | A | **Confirmed approved** |
| `haw:Orchid` | A | `V18 dyn3` | Public advice when supported, plus evidence. | A | **Confirmed approved** |
| `jap:Cherry Blossom` | A | `V19 dyn2` | Public advice when supported, plus evidence. | A | **Confirmed approved** |
| `mex:Dahlia` | A | `V18 dyn2` | Public advice when supported, plus evidence. | A | **Confirmed approved** |
| `mex:Jaguar Plushie` | A | `V18 dyn3` + R, native timing retained | Public advice when supported, plus evidence. | A + R | **Approval unknown** |
| `swi:Edelweiss` | A | `V19 dyn9` | Public advice when supported, plus evidence. | A | **Confirmed approved** |
| `uae:Tribulus Omanense` | A | `V18 dyn3` | Public advice when supported, plus evidence. | A | **Confirmed approved** |
| `uni:Heather` | A | `V18 dyn3` | Public advice when supported, plus evidence. | A | **Confirmed approved** |
| `arg:Monkey Plushie` | B | `V20 traj3` + R and `MONKEY_HOUR_LAST4_MINUTE_BASE_REPAIR_V2`, one-minute refinement | Public advice when supported, plus evidence. | B + R | **Approval unknown** |
| `can:Wolverine Plushie` | B | `V20 traj12` + R, native timing retained | Public advice when supported, plus evidence. | B + R | **Approval unknown** |
| `cay:Stingray Plushie` | B | `V20 traj5` + R and `STINGRAY_PRESERVE_VALID_V1` publication timing | Public advice when supported, plus evidence. | B + R | **Approval unknown** |
| `chi:Peony` | B | `V20 traj12` | Public advice when supported, plus evidence. | B | **Confirmed approved** |
| `sou:African Violet` | B | `V20 traj11` | Public advice when supported, plus evidence. | B | **Confirmed approved** |
| `sou:Lion Plushie` | B | `V20 traj12` + R, front targeting, native timing scorer bypassed | Public advice when supported, plus evidence. | B + R | **Approval unknown** |
| `chi:Panda Plushie` | C | `V19 dyn1` | Public advice when supported, plus evidence. | C | **Approval unknown** |
| `sou:Xanax` | C | `V19 dyn6` + `SA_RECENT4_HOUR_RATE_SUSTAINED_RISE_V1` stock forecaster | Public advice when supported, plus evidence. | C + S | **Approval unknown** |
| `uae:Camel Plushie` | C | `V19 dyn3` + R, post-event median and front targeting, native timing scorer bypassed | Public advice when supported, plus evidence. | C + R | **Approval unknown** |
| `uni:Nessie Plushie` | C | `V19 dyn8` | Public advice when supported, plus evidence. | C | **Approval unknown** |
| `uni:Red Fox Plushie` | C | `V18 dyn1` | Public advice when supported, plus evidence. | C | **Approval unknown** |
| `uni:Xanax` | C | `V19 dyn8` + conditional `extend_current_stock` median-depletion continuation | Public advice when supported, plus evidence. | C | **Approval unknown** |
| `can:Xanax` | D | `V18 dyn2` + full causal history and current-stock leave-now branch | Public row, stale. Advice suppressed. | D | **Approval unknown** |
| `swi:Chamois Plushie` | D | `CHECKPOINT4 original24_strict31_arrival_labels_v2` + V169 original 24-expert checkpoint selector. Latest published row abstained with no selected expert. | Public row, stale. Advice suppressed. | D | **Approval unknown** |

### Exact records and scope

- **A — first-ten authorization.** The release records owner authorization for a ten-item live beta and names the ten frozen engine/config pairs in the operation sequence. The release commit records 69 focused scheduling, publication, evidence, web, and rollback tests. Jaguar's original timing assignment is in scope. Its later stock guard revision is recorded separately under R. [Authorization](https://github.com/fungjkTorn/torn-fren/blob/1e508b83f8c9c042d91381b30533778fbd6b28a6/docs/FIRST_TEN_LIVE_BETA_DEPLOYMENT.md), [frozen assignments](https://github.com/fungjkTorn/torn-fren/blob/1e508b83f8c9c042d91381b30533778fbd6b28a6/docs/FIRST_RELEASE_OPERATION_SEQUENCE.md), [test record](https://github.com/fungjkTorn/torn-fren/commit/1e508b83f8c9c042d91381b30533778fbd6b28a6).
- **B — original challenger authorization.** The October 29 rollout record expressly documents user approval for the six named V20 assignments in labelled live forward testing, plus verified publication and model identity checks. The later Monkey V1 release record describes a different combined policy from the installed V2. Wolverine, Stingray, Monkey, and Lion now also carry R. The approval record for the original configurations does not establish authority for those exact revised combinations. [Challenger authorization and activation](https://github.com/fungjkTorn/torn-fren/blob/7ca92261befeabcc62f34cbcda94fd8c2ad2412c/docs/FORWARD_BETA_16_ROSTER.md), [Monkey V1 release](https://github.com/fungjkTorn/torn-fren/commit/4a58ea39d7e82b76a3ed33757464b1419de7ebb2).
- **C — next-six historical validation.** The October 22–29 causal replay names all six base timing assignments and records identity checks, simulated arrival outcomes, and the UK continuation. It records no deployment or promotion. The earlier roster expressly held UK Xanax pending the continuation work. The later reconciliation PR reports native staging. Neither record establishes public approval of the exact installed policies. Camel and South Africa Xanax also have the later policy changes listed above. [Next-six replay](https://github.com/fungjkTorn/torn-fren/blob/0e06555192abe9e51b323a8b0843efe3c60a6914/docs/NEXT_SIX_WEEK_REPLAY_20261029.md), [staging](https://github.com/fungjkTorn/torn-fren/pull/18).
- **D — final-pair validation and gaps.** The October 29 roster lists Canada Xanax and Swiss Chamois for further challenger work. PR #18 records native staging of two final-pair items and a Chamois receipt projection fix. The operations issue traces the public wrapper and separate Japan path. The October 7 Canada benchmark tests a different nearest-neighbor planner. The separate Chamois protocol compares `zero_path_cycle_median70` with `zero_path_aligned_analog70`, different from the installed checkpoint selector. These records establish runtime validation or research context. No exact-version owner approval for either public final-pair model was located. [October 29 roster](https://github.com/fungjkTorn/torn-fren/blob/7ca92261befeabcc62f34cbcda94fd8c2ad2412c/docs/FORWARD_BETA_16_ROSTER.md), [native staging](https://github.com/fungjkTorn/torn-fren/pull/18), [operations checkpoint](https://github.com/fungjkTorn/torn-fren/issues/16#issuecomment-6829893219), [Canada benchmark](https://github.com/fungjkTorn/torn-fren/blob/75393fda9e825e89c07e0657d56360f05b65d153/research/uk_canada_xanax_research_checkpoint_2026-10-07.md), [Chamois protocol](https://github.com/fungjkTorn/torn-fren/blob/main/docs/CHAMOIS_FIXED_FORWARD_VALIDATION_20261015.md).
- **R — deployed November 14 policy validation.** The live markers identify Jaguar, Monkey, Wolverine, Stingray, Lion, and Camel. The release record covers a frozen historical week, sample/guard contracts, six captured item CLI checks, the Monkey residual correction, and Camel and Lion front targeting. The released code and validation establish the variant and its tested scope. Explicit owner approval of these six exact revised combinations was not located in the records reviewed. [Reviewed release evidence](https://github.com/fungjkTorn/torn-fren/blob/57e27d6c26ef13fc57094a485f970f50735fe0a1/docs/REVIEWED_PLUSHIES_20261114.md), [review PR #30](https://github.com/fungjkTorn/torn-fren/pull/30).
- **S — separate South Africa stock policy.** The running next-six scheduler binds the item-specific rate forecaster, and the row carries its exact version marker. The newer six-plushie release excludes South Africa Xanax. The early next-six replay validates the V19 timing baseline and does not establish accuracy or approval for the installed rate forecaster. [Captured South Africa policy implementation](https://github.com/fungjkTorn/torn-fren/blob/production/vm-source-20261112/services/reviewed_foundation.py).

**Research-only comparison outside the 24.** Japan Xanax is **explicitly experimental** in the private prospective lane. `torn-fren-japan-private.service` runs the versioned final-pair module in private-Japan mode with `JAPAN_QUANTITY_RATE strict31` and stock forecaster `true_zero_quantity_rate_v1`. It writes `japan-private/latest.json` and evidence. The public bridge does not add this output to the 24, although Japan Xanax can appear as an All Items catalog entry. Preserve the private recorder and its evidence. [Recorded private role](https://github.com/fungjkTorn/torn-fren/issues/16#issuecomment-6827461581).

## Canada screenshot symptom

The screenshot itself was unavailable for inspection. The reported combination of fresh stock and **“Stock data delayed”** matches the runtime evidence:

| Signal | November 18, EST |
| --- | --- |
| Fresh collector | The successful poll and the latest Canada Xanax point, **623 stock**, both showed **7:50:27 p.m.**, around 13 seconds before the initial check. A subsequent Canada receipt at **7:51:58 p.m.** reported a country update at **7:51:27 p.m.** |
| Expired forecast | Final-pair last published at **12:38:36 p.m.** using a **12:38:27 p.m.** heartbeat. The snapshot expired at **12:41:27 p.m.** |
| Public response | Around **7:50 p.m.**, the board returned HTTP 200 and 24 rows. Canada Xanax and Swiss Chamois had `STALE_DATA` and no departure timestamps. The deployed forecast UI's **“Stock data delayed”** text is a stale-advice branch. The All Items browser can render **“Forecast expired”** for the same expired forecast. |

The chart and publisher have independent freshness clocks. The chart can show recent stock while the website suppresses advice from an expired final-pair publication. The observed gap is consistent with the final-pair service failure in the main audit. It leaves model selection and approval open.

## Before restarting repair work

Record the exact model and policy revision, allowed public or research role, and owner decision for Canada Xanax and Swiss Chamois. A successful publisher repair would restore advice from the currently wired assignments, so production repair and rollout stay on hold until those assignments are reviewed. Keep the services, existing outputs, stock and historical datasets, Discord, and ongoing research evidence intact.
