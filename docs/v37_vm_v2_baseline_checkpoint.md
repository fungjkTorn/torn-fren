# V37 reference-only timeout fix — VM checkpoint

The live V36 Heather manual pilot returned:
`native_status=RESEARCH_PROPOSAL_ONLY`, `champion_executed=true`,
`v2_status=PUBLIC_HISTORY_TIMEOUT_OR_ERROR`.
A direct `/api/history?country=uni&item=Heather&minutes=60`
request subsequently returned HTTP 200 in **2.23 seconds**, V2 status
`using_future_reachable_cycle`, and
`analysis.prediction_v2_stale=true` with future departure and arrival.
The 3-second V36 research timeout was too close to ordinary VM latency.

Changes: only the standalone V36 research sampler and its tests.
- HTTP baseline timeout from 3s to **10s**, preserving the fixed loopback
  address and no-token policy.
- Distinguishes `PUBLIC_HISTORY_TIMEOUT` from
  `PUBLIC_HISTORY_CONNECTION_OR_FORMAT_ERROR`.
- Saves `v2_status=available_stale` when `prediction_v2_stale=true`,
  rather than silently treating a cached forecast as freshly computed.
- The frozen V18 model worker remains bounded to 38s; the research unit's
  75s startup cap and CPU/memory isolation remain unchanged.
- No code change to the production web app or poller. Timer stays OFF until
  successful manual end-to-end verification.

## Operator next step (while research timer paused)

```bash
cd /opt/torn-fren
test "$(git branch --show-current)" = profitability-v1 || exit 2
test -z "$(git status --porcelain)" || exit 2
git fetch origin release/v37-v2-baseline-timeout-20261008
git merge-base --is-ancestor HEAD FETCH_HEAD || exit 2
git branch "backup/pre-v37-$(date +%Y%m%d-%H%M%S)" HEAD
git merge --ff-only FETCH_HEAD
python3 -m unittest discover -s tests -p 'test_v36_isolated_museum_sampler.py' -v

# Use a NEW manual experiment ID to avoid mixing with the prior failed run.
time sudo -u ubuntu nice -n 15 timeout 60s python3 -m \
  research.v36_isolated_museum_sampler \
  --db /opt/torn-fren/data/stock_history.db \
  --evidence-db /var/lib/torn-fren-shadow/capture.db \
  --experiment pilot-v37-manual-heather \
  --item 'uni:Heather'
```

Expected: `champion_executed=true`,
`native_status=RESEARCH_PROPOSAL_ONLY`,
`v2_status=available` or `available_stale`. A timeout should be
investigated; this is a bounded live test, not guaranteed to succeed.
The manual process still uses only the *research* DB for writes.

**Do not install/re-enable the systemd timer until this verification passes.**
The live service unit is still the older V35 four-item sequential service
unless the operator explicitly installed a later template. Once the manual
test passes, copy and start the separate V36 unit as documented in
`docs/v36_vm_isolated_museum_recovery.md`, verify one isolated capture, then
only after successful service checks enable the timer.
