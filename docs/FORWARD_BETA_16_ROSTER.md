# Expansion from ten to sixteen live forward-test items

The user approved moving the six evaluated plushie/flower challengers to labelled live forward testing. The original ten retain their configurations, publisher unit, model SHA and append-only evidence. UK Xanax is held until current-stock continuation is corrected and checked; no unconditional leave-now rule is introduced.

The six use the exact tested V20 configurations with full available causal history. The 48-hour Lion restriction and all point-count lookbacks stay removed. No arrival margin is added. Historical rescore rates are not copied into prospective metrics.

## Original 25-item roster

| Item | Status | Configuration or next step |
| --- | --- | --- |
| arg:Ceibo Flower | Existing live ten | v18 dyn3 |
| arg:Monkey Plushie | Ready for six-item deployment | v20 traj3; full history |
| can:Crocus | Existing live ten | v18 dyn5 |
| can:Wolverine Plushie | Ready for six-item deployment | v20 traj12; full history |
| can:Xanax | Remaining | Further challenger work |
| cay:Banana Orchid | Existing live ten | v18 dyn7 |
| cay:Stingray Plushie | Ready for six-item deployment | v20 traj5; full history |
| chi:Panda Plushie | Remaining | Scheduling corrected; actual-data pilot/week replay pending refreshed export |
| chi:Peony | Ready for six-item deployment | v20 traj12; full history |
| haw:Orchid | Existing live ten | v18 dyn3 |
| jap:Cherry Blossom | Existing live ten | v19 dyn2 |
| jap:Xanax | Remaining | Further challenger work; Japan Xanax needs its separate short-window approach |
| mex:Dahlia | Existing live ten | v18 dyn2 |
| mex:Jaguar Plushie | Existing live ten | v18 dyn3 |
| sou:African Violet | Ready for six-item deployment | v20 traj11; full history |
| sou:Lion Plushie | Ready for six-item deployment | v20 traj12; full history |
| sou:Xanax | Remaining | Scheduling corrected; actual-data pilot/week replay pending refreshed export |
| swi:Chamois Plushie | Remaining | Further challenger work |
| swi:Edelweiss | Existing live ten | v19 dyn9 |
| uae:Camel Plushie | Remaining | Scheduling corrected; actual-data pilot/week replay pending refreshed export |
| uae:Tribulus Omanense | Existing live ten | v18 dyn3 |
| uni:Heather | Existing live ten | v18 dyn3 |
| uni:Nessie Plushie | Remaining | Scheduling corrected; actual-data pilot/week replay pending refreshed export |
| uni:Red Fox Plushie | Remaining | Scheduling corrected; actual-data pilot/week replay pending refreshed export |
| uni:Xanax | Remaining | Fix and validate current-stock continuation / long-phase handling |

After successful deployment there will be 16 live forward-test items and 9 remaining. Before the VM apply report is verified, the six remain prepared rather than confirmed live.

## Runtime and deployment

The six have a separate immutable source release, source copy, ledger, snapshot, lock, service and timer under `/var/lib/torn-fren-live-beta/challengers`. The timer runs each minute at :50 UTC, separately from the original ten at :20 UTC. CPUQuota is 75% of one core, Nice 19, MemoryMax 1 GiB. The original ten unit is not edited or stopped. No paid capacity upgrade is involved.

Bootstrap copies only stock observations, successful/failed poll evidence, country clocks and collection gaps for the six items, retaining all available causal training history. Each run updates only this private source with a bounded read-only collector tail; the original collector is never written. It does not depend on the original ten-item export containing the newcomers.

A private CPU-limited native-engine preflight runs before changing the website or installing persistent challenger units. It has its own discarded evidence ledger, so it does not seed public results. Its batch must complete within 55 seconds to fit the minute cadence. It validates all six rows, fresh data, model identity, the full-history override, V5 evidence and zero duplicate targets. The final installed publication is checked again.

The website combines the two snapshots, retaining each row’s model SHA, evidence and expiry. Stale challenger advice pauses independently; a missing/malformed challenger snapshot leaves the original ten available. All three planner/graph views use the combined feed and each new item’s observed-history source.

`deploy/Add_Forward_Challengers.ps1 -Apply` fetches the release branch, packages source via Git, uploads it with the existing Windows SSH key, performs the preflight, stages the new units, restarts only the web service to load the additive bridge, verifies the 16-item HTTP feed with unchanged original identities, and enables the new timer. It backs up the two website files and original unit before applying. Failed verification stops/removes only the new units and restores the website. New private evidence is preserved. Exceptions and guard failures are written as JSON reports.

No GitHub Actions are used. GitHub preparation alone does not apply the VM deployment. Review the resulting report and fresh public feed before marking the six live. The existing admin-health/storage follow-up remains a separate pending task.

## First rollout guard correction

The October 29, 8:57 PM ET attempt stopped before changing the website or installing/enabling the challenger service. The installed V5 `beta.js` had CRLF line endings (36,313 bytes, SHA-256 `1e7fea55aef49765447f622c9d11efa67b31072778f2d674cbbd1ba9c3bcd767`); the reviewed LF representation was 35,956 bytes with SHA-256 `d2d856f07d181854738ad66096f541edcc1d27e15ff694b785c3e039d9859276`. Converting only CRLF to LF produces byte-identical reviewed source; there were no code changes.

The guard now accepts the exact reviewed bytes or their CRLF-equivalent representation. It does not strip whitespace, discard a BOM or ignore content edits. Any remaining difference still stops before preflight or deployment, with installed and normalized hashes in the report. Backups and rollback retain the original installed bytes. Tests cover equivalent CRLF acceptance, unchanged originals in preview, rejection of real edits before any preflight, successful deployment, slow preflight and rollback. The actual installed public script was checked against the guard.

### Runtime preflight correction

The October 29 retry passed website content review but stopped before activation
because the six-item batch exceeded the 55-second cadence budget. That report
omitted the actual runtime. No six-item deployment success has been confirmed.

Full-history native inference now reuses one frozen read-only connection and
memoizes repeated history queries within that isolated inference. Integer peak
leave-one-out means use the same exact arithmetic result without recomputing the
entire list for every cycle. Caches are discarded before the child exits; no
predictions or training rows are reused across publications. Original ten-item
inference keeps its existing path.

All six complete forecast outputs matched the previous implementation exactly
at the newest uploaded historical cutoff. Combined local native inference fell
from 10.448 to 3.200 seconds. These are local measurements, not VM guarantees.
See `SIX_CHALLENGER_RUNTIME_VALIDATION_20261029.json`. The VM must still pass the
55-second limit; the report now includes per-item and whole-run timing, including
source refresh, if it exceeds that budget. No cadence or freshness rule is relaxed.
