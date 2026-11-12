# Country clock logging: compatible activation ready for owner review

**Status: activated by the owner on October18,2026.** The reported result was COUNTRY_CLOCK_ACTIVATED with two new Japan receipts and22 exported country-clock rows (snapshot cutoff1792296722). Backup:/var/backups/torn-fren-country-clocks/20261018T041129Z-dakyjklw. Prediction models remain unchanged and no new accuracy rate is established. The commands below retain the installation record; do not repeat activation on an already updated host.

This enables measurement needed to investigate Japan's broken/stale cycle training. It does not fix or promote a prediction model or establish a new success rate.

## Installed state verified read-only

Private run39094501927, source3ec26ce13ccf01acb047d18377deccaf989f7996, inspected installed code and the sanitized research snapshot, without opening the live collector DB. Installed history code has no country_freshness.record call, services/country_freshness.py is absent, and the installed exporter has no clock-metadata support. The snapshot has no country_stock_observations table or clock metadata. Static inspection does not prove which code revision an already-running process loaded. Installed stock-provider file hash matches the checked-in YATA-first/nonempty-export fallback implementation; it does not compare country report ages.

The old Oct15 patch failed its read-only apply-check against the actual host code. A new minimal patch was generated from AST positions in that file. It adds only one import, schema initialization and one transaction-local clock recording call. Existing signatures, stock quantity/cost delta logic and unrelated host changes are preserved. Provider country-update and receipt timestamps are recorded even when stock is unchanged. Export epoch remains explicitly MISSING in this minimal patch because the old function does not receive it.

Patch-plan runs39094697885 and39094716702 succeeded. The latter artifact12123788839 contains only the addition-only patch and manifest, ZIP SHA256 e97f3a297e8fc668cc298443d211721543286d66a58cd581cb3a3d4cd862c4ae, independently verified. Host apply-check returned0; application to a disposable copy produced the expected hash. The original collector/exporter files remained unchanged. No live DB was opened and no service was controlled.

## Reviewed payload

Source pin: `1304b3580bf9f45a9d4e47dd3bb12f0d71a02c41`.

- Collector old SHA256: `532918cf8a6b802e62200fda29d3c523273ef214c608ec0b64e17ce3a27b6568`
- Collector proposed SHA256: `7b447f12b43e4a3365e9fa876b51a5c6174210650b50ec8a606ef6498dba932d`
- Addition-only patch SHA256: `46d72a0c78409cfc55a0d801931b1268ee821d73dfacc8d59b2a4c880c19d4d7`
- New helper SHA256: `00443b97a49e2736b3bc1f5e0ddd342c8ecaf18779adb8137449f59786c1c7c2`
- Installed exporter old SHA256: `ff27456029fbce539c217c4c4ddb248f9d2cdcdd3f2106e06a7a7be7f721d1dd`
- Proposed exporter SHA256: `395ad99c34271158eaaba44568e5a332719c638692f38204d9d1acca64f7b3f1`

Payload is deploy/patches/country-clock-20261018/{collector.patch,manifest.json}. Owner utility deploy/scripts/activate_country_clocks.py defaults to a read-only plan and requires explicit --apply plus sudo for activation. It refuses changed base hashes, changed ownership/permissions or an unexpected existing helper. The zero-context patch is tied to the exact old collector hash; it is never applied fuzzily to another revision.

## Owner terminal: prepare and inspect

Run in the Ubuntu VM terminal (`ubuntu@torn-fren-prod`), not Windows PowerShell:

```bash
(
set -euo pipefail
CLOCK_PIN=1304b3580bf9f45a9d4e47dd3bb12f0d71a02c41
CLOCK_CODE="$HOME/torn-fren-country-clocks-${CLOCK_PIN:0:12}"
if [ ! -d "$CLOCK_CODE/.git" ]; then
  git clone --single-branch --branch research/v38-full-roster-live-prep-20261009 https://github.com/fungjkTorn/torn-fren.git "$CLOCK_CODE"
fi
git -C "$CLOCK_CODE" fetch origin "$CLOCK_PIN"
git -C "$CLOCK_CODE" checkout --detach "$CLOCK_PIN"
test "$(git -C "$CLOCK_CODE" rev-parse HEAD)" = "$CLOCK_PIN"
python3.12 -B "$CLOCK_CODE/deploy/scripts/activate_country_clocks.py"
)
```

The expected kind is COUNTRY_CLOCK_ACTIVATION_PLAN. This does not open the live DB, install files or restart services. If hashes, permissions or existing helper differ, stop and regenerate/review the payload instead of forcing it.

## Activation: only after owner approval of the production change

```bash
sudo python3.12 -B "$HOME/torn-fren-country-clocks-1304b3580bf9/deploy/scripts/activate_country_clocks.py" --apply
```

The explicit activation:

1. Rechecks installed code and metadata, backs up original code under /var/backups/torn-fren-country-clocks with a private directory and restore index.
2. Installs the new helper, patched collector and updated exporter atomically, preserving existing file ownership/modes (collector1001:1001,0664; exporter0:0,0644; helper follows collector ownership with0644).
3. Restarts only torn-fren-poller.service. Waits at most100seconds for two distinct new Japan clock receipts and a new successful collector heartbeat.
4. Starts the existing torn-fren-research-snapshot.service and verifies fresh exported nonzero country-clock metadata.
5. On failure, restores changed code, removes the new helper and restarts the original poller. Any clock rows already collected remain; stock history is not rewritten. A concurrent external code edit stops automatic rollback for manual review rather than overwriting unknown changes. Backups and index remain available.

It does not restart the website/bot, change model assignments, enable timers, alter service configuration or modify research isolation/ACLs. Success kind is COUNTRY_CLOCK_ACTIVATED with backup location, new receipt count and snapshot metadata. This proves logging/export liveness, not country/item/game freshness or improved arrival success. Future diagnostics must inspect report ages, regressions and provider disagreement before changing continuity rules.

## Validation

Eight read-only preflight tests, two patch-generator behavioral/refusal tests, four activation/rollback tests, and four snapshot-export tests passed locally. Tests cover unchanged-stock clock writes, transaction rollback, preserving unrelated edits, exact payload hashes/modes, default read-only behavior, concurrent-edit refusal and restoration after failed verification. No test applied changes to production. Host plan dry-run and GitHub CI status are recorded in the private handoff.

## Final readiness evidence

Pinned owner utility dry-run completed successfully on the actual installed collector/exporter: private run39094976269, source1304b3580bf9f45a9d4e47dd3bb12f0d71a02c41. It confirmed all three proposed paths, exact old/new hashes and ownership/modes, with live_database_accessed=false and production_modified=false. It did not invoke activation or service operations.

All public workflows for that pin passed: safeguards39094950043, expanded adapters39094950041, V35/private pilot39094952512 and profitability compatibility39094952518. Eighteen local checks passed (8preflight,2patch preparation,4activation/rollback,4export). Activation is prepared and verified but remains unexecuted. The owner must approve the production collector restart and run the explicit --apply command. No new Japan accuracy improvement has been established.
