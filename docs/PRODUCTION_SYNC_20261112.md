# Torn-FREN production source reconciliation — 2026-11-12

Tracking: [#16](https://github.com/fungjkTorn/torn-fren/issues/16).

## Scope and safety

This is a **review-only branch** based on `release/monkey-combined-20261110` (`4a58ea3`). No VM files, services, timers, databases, or `main` are modified by this branch. Do not deploy or merge an incomplete source overlay. Preserve the complete original Git history for rollback.

The source capture is intentionally **not committed**: it contains duplicate release snapshots and must be audited for embedded configuration and secrets. Never commit `.env`, bot tokens, API keys, SQLite databases, stock/evidence data, private keys, or production log dumps.

## Verified runtime boundaries

| Runtime | Active source | Consequence |
| --- | --- | --- |
| Web/FastAPI | `/opt/torn-fren`; uvicorn `web.app:app` | UI assets are loaded from the production web root |
| Collector/poller | `/opt/torn-fren/poller.py` | Strict 30-second collection loop; model/audit work delegated to workers |
| Discord bot | `/opt/torn-fren/run.py` | Same code as GitHub; checksum drift was line endings only |
| Next-six publisher | versioned `1781fb8318f9cd943063233b7c2d1eb339b0a5f5-next-six` release | Do not replace with old first-release publisher |
| Scheduled research jobs | Separate systemd service/timer roots | Old-looking source may still be reachable |

The source capture inventoried **1,148** source files across the production root and three versioned release roots. Timer inventory found **18 installed**, **12 enabled**, **6 disabled**. Service state is not sufficient to prove whether a file can be removed.

## Verified production source digests (SHA-256)

| Source path | Digest |
| --- | --- |
| `poller.py` | `3e43d74a5148d00afead8a194872753a825d21a2ca414f22c93fb339b6404396` |
| `web/first_release_assets/beta.js` | `ac2b98c86a4d2077558b0a253299ea51d1f931e0c15a31dfe3d76efe64363304` |
| `web/first_release_assets/beta.css` | `9fe8bad697e011e92944b74eb84212fe4ba5166787c4d3a8acfc9254d75f56ef` |
| `web/app.py` | `c7a2066b3afc1a23e97bf7fe4034eaf062d56db869e4d1ab51b856207a3e500c` |
| `web/first_release_bridge.py` | `acfa71ad6b49c4ac5e0c367614df7bea2ed1c1355c0cd8830d679198d6fba8d9` |

**Important:** The bridge digest is intentionally not certified in this document; use the exact checksum from the read-only capture manifest instead of treating this shortened placeholder as a valid digest.

The production graph assets are backed up separately and have **not yet been brought into this remote review branch**. They currently exist in the owner's separate local `sync/live-website-20261111` worktree.

## Confirmed drift and safe integrations

- `run.py` differs only in LF/CRLF; no code replacement needed.
- `poller.py` differed materially. This branch copies the exact production collector-only implementation and adds isolated regression checks for provider failure and successful poll bookkeeping.
- `services/provider_freshness.py` was missing in the November 10 branch. This branch adds the exact captured production helper, with causal/clock/staleness regression tests.
- `web/app.py` and `web/first_release_bridge.py` differ; live app imports additional `web/history_cache_v39.py` and `web/v41_champion_cache.py` modules not present in the starting branch.
- The active next-six publisher additionally depends on its own `services/next_six_live.py`, `services/forward_beta_roster.py`, `services/first_release_live.py` and associated scheduling/evidence modules. The November 10 branch does **not** implement all of these contracts. Do not copy the entry point alone.
- A legacy timer cannot be retired just because the corresponding service has a failed, inactive or old-looking status. `final-pair-beta` and `japan-private` were still scheduled in the read-only inventory.

## Retirement gates

Classify every candidate as: (1) active, (2) enabled but failing/unverified, (3) research-only still scheduled, (4) truly unreachable, or (5) unknown. Archive only category 4 after verifying **all** of the following:

1. No enabled systemd unit or timer references the module or script.
2. No web route, bot command, planner selector, dynamic import, fallback, command-line launcher, or release/rollback script references it.
3. The current production and versioned publisher code have correct provenance, model-selection and stale-data behavior after reconciliation.
4. CI tests and offline smoke tests cover the three public pages, flight selector, graph assets, poller, publishers, freshness and bot commands.
5. A pre-retirement tag and reversible deletion commit exist. Deletions must be a **separate PR** from source reconciliation.

## Remaining work before merge

- [ ] Reconcile the actual web app and bridge, without regressing November 10 model/publisher features.
- [ ] Import the remaining required production helper modules and test their APIs together.
- [ ] Integrate the exact production JS/CSS snapshots and verify SHA-256.
- [ ] Reconcile next-six entry point *plus* forward roster and publish/evidence contracts.
- [ ] Audit dynamic imports, service ExecStart paths, UI routes, bot commands, and test suite compatibility.
- [ ] Prepare a separate, proven-unreferenced retirement PR.
- [ ] Only after verification, plan an explicit production deployment with rollback.

**No automatic merge or deployment is authorized by this document.**
