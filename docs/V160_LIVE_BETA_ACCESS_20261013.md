
> **LIVE BETA INSTALL FIX — OCT 13, 13:22 EDT:** The user ran the earlier beta installer, which FAILED before installing the service with `ValueError: invalid 24-item roster` in `snapshot()`. Root cause verified: pinned `research/v38_roster.json` contains **22** canonical keys, and `research.v128_full24_earliest_shadow.exact_roster()` adds **Canada Xanax and UK Xanax** to yield the actual 24-key V160 ledger. The new beta reader incorrectly demanded 24 *in the raw JSON*. Fixed in `deploy/scripts/v160_private_beta_board.py`, which validates 22 canonical keys then adds precisely the two specialist keys; test fixture now copies real pinned `v38_roster.json` and derives the true 24 identities. All four CI workflows passed at source commit `e2898e65c40753059e1e75bb1a7fab5f952fb4a1` (including real-roster snapshot and HTTP tests); revised operator at `880be16b5f7f450132abcacd2c1049d371f49c67` pins that tested source. **The prior install failed before systemd enable; beta service is NOT yet verified installed/running. The already enabled V160 recorder was not modified by this failure.** Repeat one command with the updated operator pin as shown below. 

# V160 live research beta: usable 24-item dashboard, isolated launch (Oct 13 2026)

## Purpose and verified baseline
This is a usable HTML dashboard over **the V160 private five-minute prospective ledger actually running on the VM**, not an offline simulation or a generic model tournament. The user confirmed `torn-fren-v160-forward24.timer` enabled and active, with the first immutable issue `1791910560` containing 24/24 rows. The user wants departure timing usable **now** while forward arrival evidence matures.

The new separate `deploy/scripts/v160_private_beta_board.py` serves `/` and `/api/live` on **127.0.0.1:8765 ONLY**. It requires the actual pinned 24-item roster and valid, complete latest SQLite issue, and reads `v160_v151_prospective24.db` using SQLite mode=ro/query_only. It presents both model variants per item, local-time departure and arrival, countdown, observed last quantity, flight length, dual-model agreement/disagreement and search/sort/filters. Every 30 seconds the client refreshes; every second the countdown rerenders. If collector heartbeat at issuance is older than 180s, issue capture latency >90s, or the latest issue is older than 660s, **all candidate departure times are hidden**. Already-passed departures are also withheld. It never claims live calibrated success, verified current per-country stock, or real player flights.

A new `torn-fren-v160-beta-board.service` is **optional and additive** (separate new service only). It runs as ubuntu, loops back to 127.0.0.1, has CPUQuota=5%, MemoryMax=128M, read-only filesystem, no production website/collector modification, no public ports, no game automation. The guarded `deploy/scripts/v160_private_beta_operator.sh` supports `install`, `status`, `stop`, refuses different pre-existing service code and checks a real fresh complete 24-row issue before enabling. Only `install` changes that **new** private service; it never enables/disables the V160 capture timer. The operator sources its board/service pair from immutable tested research commit `e2898e65c40753059e1e75bb1a7fab5f952fb4a1`.

Tested on GitHub Actions research branch: live beta ledger/HTTP/stale/integrity/flight and service isolation tests. [Passing live beta CI](https://github.com/fungjkTorn/torn-fren/actions/runs/38436762128) at operator commit `880be16b5f7f450132abcacd2c1049d371f49c67`.

## ONE Windows PowerShell block: install private beta and open tunnel

This is the smallest available route to a working private user interface without risk to the two deployed production website views. The script cannot run on behalf of the user without VM credentials; the user must execute it **once** on their Windows PC where SSH keys already work.

```powershell
$key = "C:\Users\fungb\Desktop\.ssh\torn-fren.key"
$remote = "ubuntu@150.136.108.146"
$branch = "research/v38-full-roster-live-prep-20261009"
$pin = "880be16b5f7f450132abcacd2c1049d371f49c67"
$operator = "deploy/scripts/v160_private_beta_operator.sh"

if (-not (Test-Path -LiteralPath $key)) { throw "SSH key missing" }

$base = "cd /home/ubuntu/torn-fren-v38-probe && git fetch -q origin $branch && git show " + $pin + ":" + $operator
& ssh -i $key $remote ($base + " | bash -s -- install")
if ($LASTEXITCODE -ne 0) { throw "Private beta installation failed: $LASTEXITCODE" }

& ssh -i $key $remote ("cd /home/ubuntu/torn-fren-v38-probe && git show " + $pin + ":" + $operator + " | bash -s -- status")
if ($LASTEXITCODE -ne 0) { throw "Private beta status failed" }

Write-Host "OPEN IN BROWSER: http://127.0.0.1:8765/"
Write-Host "Keep this PowerShell window open to retain the SSH tunnel."
& ssh -i $key -N -o ExitOnForwardFailure=yes -L 8765:127.0.0.1:8765 $remote
```

The SSH tunnel exposes only port 8765 **on the user's own computer**. The private web app remains bound to VM loopback. Closing PowerShell/Ctrl+C closes the SSH tunnel but does not stop the isolated private beta service or the separate prospective recorder. To reconnect after an existing installation, use:

```powershell
ssh -i "C:\Users\fungb\Desktop\.ssh\torn-fren.key" -N -o ExitOnForwardFailure=yes -L 8765:127.0.0.1:8765 ubuntu@150.136.108.146
```

To stop ONLY the isolated beta web service (not the collector or V160 recorder), use the exact same pinned operator with `stop` rather than `install`.

## Important production integration limitation
A localhost-only private research board is **not equivalent to public website deployment**. Both existing detailed graph `/` and experimental 24-item dashboard `/experimental` remain untouched. The deployed /experimental HTML and web/app.py differ from the checked-in GitHub research checkout. Do not blindly overwrite them. Next step: run existing read-only deployed-source inspection (`deploy/scripts/v142_inspect_existing_experimental.sh`), verify precise routes/configuration/source hashes, then build **additive** production integration and rollback. Do not expose raw 0600 research SQLite to the web user or change permissions; use a dedicated access-controlled read-only bridge, or a carefully reviewed internal proxy, to preserve privacy. Do not serve uncertain research predictions as guaranteed GO.

## What is / isn't verified
- **Verified:** GitHub code/test suites, correct 24-row validation, private HTTP 200 on fresh fixture, 503/hide stale, exact flight duration, no DB writes, new unit isolation.
- **Verified by actual user VM logs:** V160 recorder active, first 24/24 immutable issue exists.
- **NOT yet verified on VM:** dedicated beta board installed/running, browser access at localhost:8765, public-site route, ongoing 24/24 recurrence after the first issue, genuine forward arrival success %, per-country provider freshness, Japan Xanax qualified departures.

Prioritize getting the first page actually opened on the user's browser before building more models.
