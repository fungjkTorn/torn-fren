# Checkpoint 14 — private-overlay wiring verified; fresh deployment baseline pending

Public source tested: `7e526ef891cf958f3d7d85e3da111e33ad7fe703`. Private overlay: `b44965df2d863c9c592eb23d1a30a50340aa3707`, stripping `runtime-overlay/`. All four overlay files were verified against their recorded Git blob hashes. Private source remains outside public Git.

Three additional isolated staging checks passed: Chamois resolved-cache save/load and wrong-model identity rejection; actual public Canada/Chamois launcher-to-publisher publication; separate private Japan launcher-to-publisher publication. Tests execute real refresh_tail, public publisher, ledger writes, decision construction and cache paths on synthetic databases, verifying the collector bytes remain unchanged. Native forecast fitting is stubbed: these are interface and isolation tests, not new accuracy evidence or proof of VM deployment parity.

All nine existing integration workflows passed on the source commit. No merge, production code update, timer/service change, database modification or VS Code update was performed in this checkpoint.

## Next deployment gate

A read-only operator preflight is prepared to capture current critical source digests, active working directories, wrapper/ExecStart digests (without exporting arguments), service/drop-in state, local publication freshness/counts and collector heartbeat age. This is required because the prior healthy final-pair report proves a single instant and leaves the reproducible V169 receipt projection bug installed.

Use the baseline to build a versioned candidate and validate the five publisher entry points and external wrappers before switching paths. Preserve existing model identities, caches, inference sources, pending forecast ledgers and private Japan isolation; do not repoint only the web root and assume publishers follow it. Preserve exact old source/drop-ins for rollback. Do not delete production state or archive further code during this gate.

After candidate validation: controlled main integration, guarded VM source alignment and publication verification across scheduled ticks, then safe local VS Code synchronization. Do not reset or clean the owner's working directory; prefer a new checkout of the verified main commit. No automatic deployment is performed by this document.
