# VM prospective forward recording reliability — 2026-10-21

The original heavy private GitHub workflow ran every five minutes but regularly lasted ~25 minutes. Research snapshots refreshed ~30 minutes, while the prospective recorder requires at most 160 seconds of poll age. Previous overnight trials correctly recorded zero issues, and the heavy workflow sometimes hit protected V160 paths.

## GitHub changes (research only)

- Private research workflow .github/workflows/physical-forward-fast.yml independently attempts genuine frozen 24-item forward issues every five minutes on the restricted private runner, uses an append-only private sidecar, and scores mature observations only.
- Automatic five-minute historical replays were removed from .github/workflows/forecast-research.yml; manual and explicit push workflows remain available.
- GitHub-hosted controls tests verify restricted permissions, a genuinely fresh source, and no historical-workflow five-minute cron.
- Public research exporter deploy/research_runner/export_snapshot.py now preserves only the nonsecret provider label in sanitized poll_heartbeats, if the original collector supplies it. If absent, source continuity remains unverified.
- Public deploy/research_runner/tune_snapshot_for_forward.sh checks the source and isolation, verifies the new exporter against a temporary 14-day sanitized snapshot, backs up the installed exporter, validates a full snapshot, then adjusts only the research snapshot timer to 2 minutes (10-second accuracy). CPU 40%, memory 640 MiB, source query-only access, account ACLs, V160 and websites remain unchanged.

## Deployment boundary

The private GitHub runner intentionally cannot edit root-owned VM systemd or install the exporter. One reviewed command run by the VM ubuntu owner is required. The script is read-only by default and needs --apply.

Windows PowerShell command after review:

    $branch = 'research/v38-full-roster-live-prep-20261009'
    $commit = 'd965c050aeeadff145c20ba43c4ff1930c4626af'
    $key = "$env:USERPROFILE\Desktop\.ssh\torn-fren.key"
    $hostName = 'ubuntu@150.136.108.146'
    $command = "cd /home/ubuntu/torn-fren-v38-probe && git fetch -q origin $branch && git show ${commit}:deploy/research_runner/tune_snapshot_for_forward.sh | bash -s -- --apply"
    ssh -i $key $hostName $command

Do not report forward collection successful merely because an Actions job concludes successfully: require FORWARD_FAST_ISSUE with status RECORDED_IMMUTABLE_ISSUE and forward_items_recorded=24. Once the research snapshot refresh cadence is applied, monitor the isolated exporter CPU/timeouts, actual freshness, and post-issue scoring results.

Restock accuracy within +/-5 and +/-10 minutes and simulated landing stock>=30 at landing+10s are separate provisional metrics. Poll-bracket observations are not exact game server timestamps or proven real player flights. This experiment has NOT changed item-specific champion assignments, live collector or user website.
