# Torn Fren — small main-based private shadow canary (October 8, 2026)

This release does **not** publish any new item-specific champion recommendations.
The existing `/api/history` Prediction V2 behavior is unchanged.
All provisional model selections remain `RESEARCH_ONLY_BLOCKED`.

## Before merging
- GitHub Actions `Production-canary isolation gate` must pass. It runs 18 unit/synthetic integration tests, including the original generic planner; the production VM and real user data are **not** exercised.
- Review the 10 scoped files in the PR. No database, API keys, SSH credentials or passwords belong in git.
- Original core web app only imports an endpoint and registers it before the catch-all static mount.
- Two flags are **OFF by default**: `TORN_FREN_CHAMPION_SHADOW_ENABLED`, `TORN_FREN_CHAMPION_SHADOW_NATIVE_ENABLED`.

## VM rollout stage A — installation (safe/no player-visible model changes)
1. Back up the deployed Git revision, .env/config and service state, using the VM's normal runbook. Do not copy secrets to GitHub.
2. Install the reviewed main-branch commit using the VM's existing checkout/deployment process. This repository does **not** contain a trusted server-deployment workflow; merging GitHub alone does not verify the VM has updated.
3. Leave **both flags unset/0**. Restart only the Torn Fren web service using its known service manager.
4. Check `/api/catalog`, a known working `/api/history?country=can&item=Fire%20Hydrant` request, and existing Discord operation; compare V2 response shape with pre-deployment. Check `/api/research/champion-shadow?country=can&item=Fire%20Hydrant` returns HTTP **404** when the flag is off.
5. If any health/route regression appears, revert the main-based canary deployment and restart with the original code. Do not change the collector DB.

## Stage B — authenticated V2-reference diagnostic
- Only after stage A smoke passes, configure a new randomly generated >=32 character token in the VM's private environment. Restrict it to an operator; never paste it into a GitHub issue, chat, query string or logs.
- Enable `TORN_FREN_CHAMPION_SHADOW_ENABLED=1` while keeping `TORN_FREN_CHAMPION_SHADOW_NATIVE_ENABLED=0`. Restart service.
- Verify unauthenticated private request returns 403; authenticated header `X-Torn-Fren-Shadow-Token` returns 236-catalog candidate identity, with `champion_executed=false`. The private response contains only V2 reference departure timestamps.
- Keep any testing local or behind a private network if practical; HTTPS is required before sending private header over a network.

## Stage C — small private generic native shadow (no public forecast replacement)
- Provide on the VM **separately** the frozen V19/V20/V21 research JSON master files and their pinned SHA256 hashes. Also provide the live collector SQLite path (read-only).
- Do **not** commit either the collector DB or private credentials.
- With a working recent poll-cycle heartbeat and no collection gap, enable `TORN_FREN_CHAMPION_SHADOW_NATIVE_ENABLED=1`. It supports generic V19/V20/V21 candidates, **not** seven plushie specialists, Japan Xanax, 30 depart-now baselines, low-quantity or sparse labels.
- Start with **one or two known complete generic items** and limit request rate. Each private candidate launches a bounded child subprocess (35s timeout). Monitor CPU, memory, request latency, collector database file checksum, log errors and stale/gap rejection. Do not fan out to all 236 simultaneously.
- If source is stale, master digest does not match, request times out or model config differs from registry, the challenger must refuse to return a departure. V2 stays in the public endpoint regardless.
- Stop private testing by setting either flag back to 0, then restart. Verify private route returns 404 again.

## Stage D — prospective validation before public recommendations
- Use the separately researched evidence-capture and scoring tools on isolated, authenticated private results; **these tools are NOT part of this thin live-canary PR**.
- Capture recommendations before observing outcomes; score 30+ eligible starts and 8+ distinct resolved cycles per item, proper >=30 quantity on arrival/+10s, coverage >=95%, causal prefix independence, approved rollback.
- The current 236 registry's `all_live_promotions_prohibited` flag MUST remain true until individually approved.
- No automatic Torn action, travel command, Discord advice switch or individual-trip success probability is authorized by a private canary.

## Important independence and correction
The V31 worker embeds the strictly read-only history installer and minimal policy constants instead of importing `services/frozen_champion_shadow_v24.py` from main, which currently has a syntax error in its research replay code. This avoids altering unrelated research files on the production branch. CI validates the isolated worker module against synthetic collector stock, but **not** actual on-VM throughput or true forecast accuracy.
