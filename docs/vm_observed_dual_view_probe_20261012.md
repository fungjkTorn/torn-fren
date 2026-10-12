# VM dual-view and V128 recorder observations — 12 October 2026

Evidence: user-provided Windows PowerShell SSH transcript (V128 health and V142); NOT inferred from repository simulations. Read-only logs, API inspection and fingerprints. No private keys, API tokens, response bodies, or database records saved here.

## Existing website (V142)

- Original V2 detailed graph `/`: **HTTP 200**, 73,774 bytes.
- Existing multi-item page `/experimental`: **HTTP 200**, 12,459 bytes.
- `/api/experimental/v41/predictions`: **HTTP 200**, 24 records, **24 unique expected item keys**, zero duplicate/missing/unexpected keys.
- Existing `experimental.html` was present, as were `index.html` and `admin.html`.
- `v87_dropin_exists=true`. All 21 incumbents and 3 preview entries were present in the API. This verifies the exposed **roster**, not forward prediction accuracy or safe-to-fly guidance.
- Deployed `/experimental` HTML SHA256: `a9a47e0fe7d9b8139322873f27b31209862a8805296a9e5070ce7ff599069aa7`.
- Deployed `app.py` SHA256: `86e84488655ab8e83fc86965c846f13ff17da27b0f8edbeac3bf5f3e583a2657`.
- **Need actual deployed source for semantic merging.** Fingerprints/endpoint schema are NOT a replacement for source reconciliation.
- V41 counts at one point in time: 16 `RESEARCH_PROPOSAL_ONLY` (`actionable=true`), 5 `DEPARTURE_PASSED` (no departure shown), 3 `RESEARCH_PREVIEW_UNVALIDATED` (`actionable=false`; Panda, Lion, Japan Xanax).
- `actionable=true` on a research proposal is **not a certified >=30 at landing** success claim.
- The three preview mappings were `chi:Panda Plushie` = `PAIR_SELECTOR_UNVALIDATED selector/b`; `sou:Lion Plushie` = `PAIR_SELECTOR_UNVALIDATED selector/a`; `jap:Xanax` = `JAPAN_V8_REGIME_UNVALIDATED V8_rolling_ridge_alpha3_regime`.
- Two existing V19 Xanax entries use lower-case `model_family: "v19"` in live API, despite canonical `V19` in manifest: `can:Xanax`, `uni:Xanax`. Preserve the visible live source and match canonical model identity using a safe case alias; do not treat them as separate algorithms.
- This inspection does not prove the rendered page behaves correctly on mobile, has accurate timers, or uses the same model sources as the research checkout.

## V128 recorder/timer health

- Both `torn-fren-v128-full24-shadow.timer` and `torn-fren-v38-private-shadow.timer` reported **active**.
- V128 last reported service state: `Result=success`, `ExecMainStatus=0`, inactive/dead *between* scheduled one-shot executions.
- V128 service failed once at **22:29 UTC**: `sqlite3.OperationalError: unable to open database file` in `v60_private_snapshot_probe.read_heartbeat` while consulting `poll_heartbeats`. Root cause not established. Don't dismiss as solved by subsequent success; watch frequency.
- V128 successfully recorded complete 24-item research batches at 22:34, 22:39 and 22:44 UTC. Collector heartbeat ages in those messages: 17, 21, 19 seconds respectively, **not independent country/item feed freshness certification**.
- Decision status counts: 22:34 = 20 ABSTAIN_CURRENT_PHASE_ONSET_UNKNOWN, 3 EARLIEST_NOW, 1 EARLIEST_WAIT_SUPPORTED. 22:39 = 18 abstained, 6 now. 22:44 = 17 abstained, 7 now.
- The last as-issued sample thus abstained **17/24** (70.8%) and proposed now for **7/24** (29.2%). These counts are NOT landing success rates. The sample illustrates coverage/abstention as a beta metric and suggests phase-onset observability is a substantive issue to audit.
- Recorder writes to the private V128 sidecar only. Logs cannot establish that each recommendation was successful or that the website uses V128.

## V139 audit NOT completed

The user's first audit command stopped after `ssh.exe : From https://github.com/fungjkTorn/torn-fren`. PowerShell turned `git fetch`'s normal stderr output into an error record under `2>&1 | Tee-Object`. No `===== VERIFY APPROVED READ-ONLY INPUTS =====` / audit summary appeared. Do not interpret this as a completed evaluation.

Recommended retry, in same PowerShell session, with **no redundant outer git fetch** and with the remote script's stderr redirected to its stdout. Do NOT use local `2>&1`:

~~~powershell
$auditLog = Join-Path $HOME 'Desktop\torn-fren-v139-audit.txt'
& ssh -i $key $remote 'set -o pipefail; cd /home/ubuntu/torn-fren-v38-probe && git show 112d574d9767912367fb8fcaf0870828f1de0e82:deploy/scripts/v139_run_enhanced_departure_morning.sh | bash 2>&1' | Tee-Object -FilePath $auditLog
Write-Host "SSH exit code: $LASTEXITCODE"
~~~

The previously executed `git fetch` already downloaded branch metadata before PowerShell encountered stderr, and the pinned V139 script commit predates V142, so it is expected to be present in the repo. If `git show` fails, capture the error and avoid improvising commands.

Once V139 executes, evaluate original V2 vs V75 vs V128 **frozen as-issued** results and censored unknowns. The three original at-home checks remain sufficient for this immediate evidence collection.
