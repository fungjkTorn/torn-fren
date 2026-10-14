# Private research runner setup — independent model testing

This is a **one-time, opt-in** project setup. Do **not** register a self-hosted runner to the public `fungjkTorn/torn-fren` repository. GitHub warns that executing untrusted workflow code on self-hosted runners can compromise the host. The controls below limit the runner to a separately sanitized stock-history snapshot, but the safest alternative is an entirely separate VM.

## 1. User creates private repository

At [GitHub: New repository](https://github.com/new), owner `fungjkTorn`, create **`torn-fren-research-private`**, visibility **Private**, initialize with README. Do NOT fork the existing public repo. Configure the connected GitHub app to include this new private repository if your existing installation only grants access to selected repositories.

Tell ChatGPT once the repository is created; it will verify access and install the private workflow and initial approved source pin. Never send private runner registration tokens, passwords, SSH keys, or Torn API keys through chat.

## 2. One-time sanitized snapshot exporter on existing Oracle VM

The exporter copies only 24 allowlisted foreign-stock item timestamps, quantities, providers, successful poll heartbeats and collector gaps from the collector into `/var/lib/torn-fren-research/stock_history_research.db`. It explicitly omits other tables and user/API fields, opens the live DB read-only, builds a separate temporary SQLite file, and atomically replaces the research copy. The new timer refreshes every ~30 minutes. CPU/memory/runtime limits apply. The install script adds an unprivileged user `tornresearch`, but installs **no GitHub runner** and changes no existing Torn-Fren services.

Use the verified installer from the research branch and read its final output:

```powershell
$key = "C:\Users\fungb\Desktop\.ssh\torn-fren.key"
$remote = "ubuntu@150.136.108.146"
$branch = "research/v38-full-roster-live-prep-20261009"
$installer = "fc82f4498c31c424c65a3b86ee3f2eee8db93bfd"
$command = "cd /home/ubuntu/torn-fren-v38-probe && git fetch -q origin $branch && git show " +
  $installer + ":deploy/research_runner/install_snapshot_exporter.sh | bash -s"
& ssh -i $key $remote $command
Write-Host "Research snapshot installer exit code: $LASTEXITCODE"
```

**STOP if it does not print `SUCCESS: sanitized read-only 24-item stock dataset`.** In particular it refuses to proceed to runner installation if the isolated Unix account can read the live collector or pinned research stage. Do not loosen source permissions or give the account sudo access to bypass this guard.

## 3. Prepare the isolated Python environment

When the snapshot installer succeeds, still on the VM, install a separate minimum Python environment for the research service account (not production's .venv):

```bash
sudo -H -u tornresearch python3 -m venv /var/lib/torn-fren-research-runner/.venv
sudo -H -u tornresearch /var/lib/torn-fren-research-runner/.venv/bin/python -m pip install --disable-pip-version-check --no-input "numpy>=1.24,<3"
sudo -H -u tornresearch /var/lib/torn-fren-research-runner/.venv/bin/python -c "import numpy; print(numpy.__version__)"
```

If `python3 -m venv` reports the `python3-venv` package is missing, stop and ask for a targeted fix before continuing.

## 4. Register a runner to the PRIVATE repository only

GitHub private repository → **Settings → Actions → Runners → New self-hosted runner → Linux x64**. Follow the GitHub-supplied, current download **and checksum verification** steps. Open a research-user shell with `sudo -H -u tornresearch bash`, and work directly in `/var/lib/torn-fren-research-runner` (do NOT create a nested `actions-runner` directory). Configure the runner against **only** `https://github.com/fungjkTorn/torn-fren-research-private`, with runner label `torn-fren-research`, and a unique runner name.

The GitHub registration token is short-lived and entered on the VM, **never sent to ChatGPT**. Do not run the runner directly with `./run.sh` and do not register it with the public repository.

After registration, as the `ubuntu` user, install (but don't yet start) its Linux systemd service:

```bash
sudo bash -c 'cd /var/lib/torn-fren-research-runner && ./svc.sh install tornresearch'
sudo find /etc/systemd/system -maxdepth 1 -name 'actions.runner.*.service' -printf '%f\n'
```

Choose the exact new private-repository service name from the output. Run the pinned `deploy/research_runner/harden_private_runner.sh` script using `sudo bash -s -- <service-name>`; the hardener checks that `.runner` belongs to the exact **private** research repo, applies filesystem controls and denies access to the live collector and cloud metadata, and must succeed before the runner starts. Then:

```bash
sudo bash -c 'cd /var/lib/torn-fren-research-runner && ./svc.sh start'
sudo bash -c 'cd /var/lib/torn-fren-research-runner && ./svc.sh status'
```

If GitHub registration or sandbox verification fails, stop; do not bypass the restrictions. Ask ChatGPT with the nonsecret error output.

## 5. Automatic private research tests

The GitHub connector can install the template from `deploy/research_runner/private_repo_workflow.template.yml` as `.github/workflows/forecast-research.yml` in the private repo, plus `requests/approved_model_sha.txt` containing a 40-character CI-tested public research commit.

The workflow runs on **the private repo only**, with `contents: read`, never on pull requests. It schedules comparisons every six hours and on approved model-pin changes, checks the output DB isn't stale, refuses access to the original collector, and evaluates past-only V163 restock-event recall at 15 seconds, 60 seconds and 10 minutes, including 8/16/32 recent-cycle challenger comparisons. It uploads **aggregate JSON metrics only** as a private artifact. No raw historical dataset is uploaded to GitHub.

ChatGPT can use the connected GitHub app to submit/review private research experiment commits and inspect run logs/artifacts during active sessions. Independent recurrent *analysis* between chat sessions additionally needs a scheduled agent/automation; the runner alone continuously executes experiments but does not itself generate new model ideas.

## Isolation/rollback

No original V2 graph, `/experimental`, collector, V160 recorder, or existing experiment model is changed by this setup. To stop research runs, disable the private GitHub runner in the private repository and stop its own `actions.runner.*.service`; the snapshot exporter timer can separately be stopped with `sudo systemctl disable --now torn-fren-research-snapshot.timer`. Do not remove production resources.

See [GitHub: Add self-hosted runners](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners) and [GitHub: Self-hosted runner security](https://docs.github.com/en/actions/reference/security/secure-use) for important limitations of persistent runners. A dedicated VM separate from production would provide stronger host isolation.
