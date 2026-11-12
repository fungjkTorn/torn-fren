# Source synchronization status — November 12, 2026

The attempted VM deployments failed verification and restored the original code/launches. The VM was not successfully upgraded to the reconciled GitHub main release. Do not rerun the previously generated source-sync installers.

The original objective is now handled as a source reference rather than a deployment:

- Public captured `/opt/torn-fren` source: [`production/vm-source-20261112`](https://github.com/fungjkTorn/torn-fren/tree/production/vm-source-20261112), commit `673a9a6718d4bcd7c604810306caa8f7f06cb2e4`.
- Separate publisher source roots and private code: [`torn-fren-research-private/production/vm-source-20261112`](https://github.com/fungjkTorn/torn-fren-research-private/tree/a42d0696bb942e589bc2522f26b290b7608f3cb2/production/vm-source-20261112), commit `a42d0696bb942e589bc2522f26b290b7608f3cb2`.
- All 121 non-null source checksum checks in the Nov 12 read-only VM preflight are represented exactly. Captured files outside that check retain their Nov 11 provenance. This is not a claim of a fresh complete VM export after the attempted deployments.
- 1,746 source files plus manifest and README were verified against their Git blob hashes in the private snapshot. The public reference includes 78 source files plus its status document, also byte-verified.
- Runtime databases, forecast ledgers, credentials, caches and virtual environments are not included in Git. No service restart, deployment, or source change on the VM was performed while committing the snapshot.

Use the VM-reference branch for an as-running starting point in VS Code. Public `main` retains the reconciled development version and proposed changes; its presence is not proof those changes are deployed. Windows checkout synchronization still requires a local Git operation and must not discard uncommitted work.
