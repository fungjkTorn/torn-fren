# VM source reference — November 12, 2026

This branch records the captured `/opt/torn-fren` source without deploying anything onto the VM. Files whose Nov 12 preflight checksums are available were matched byte for byte. Other captured files retain the Nov 11 export provenance. Existing repository history and supporting files are retained. This is an as-running reference, not a tested new release.

Separate publisher roots, private models, the checksum manifest and the capture-time limitations are preserved in `fungjkTorn/torn-fren-research-private`, under `production/vm-source-20261112`.

The VM remains on the original launches restored after the unsuccessful source synchronization attempts. Public main commit `090fef4b43346072ba85a24d53e80627beeba076` contains reconciled development changes and is not evidence of a completed VM deployment. Do not rerun the source-sync installers.

Use this branch as the VM-reference starting point in VS Code. Runtime databases, .env, keys and virtual environments are deliberately excluded from Git.
