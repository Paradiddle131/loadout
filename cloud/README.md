# Claude Code on the web

A cloud session's `~/.claude` starts empty, so this folder brings the setup along: the plugins, the standing rules, session hooks, and fixes for the cloud VM's known conditions.

## Set up an environment

1. Attach this repo to the environment beside the repo you work on (the target).
2. Set the environment's Setup field, naming the target:

   ```bash
   f=/home/user/loadout/cloud/setup.sh; if [ -f "$f" ]; then bash "$f" <target-repo>; else echo "loadout not cloned: setup skipped"; fi
   ```

   The guard keeps a session that starts with no repositories (a scheduled task's fresh session) from failing before Claude starts.

The setup result is cached for days; the session-start hook re-runs the setup whenever the clone's `setup.sh` or `plugins.txt` has changed since, so a merged change reaches the next session without touching the field.

## What it does

| Piece | Effect |
|---|---|
| [`setup.sh`](setup.sh) | installs this repo's plugins (read in place from the clone) and the pinned ones in [`plugins.txt`](plugins.txt), writes `~/.claude/CLAUDE.md` ([`memory.sh`](memory.sh)), turns commit and PR attribution off, installs gitleaks, points Docker at a pull-through mirror, and runs the target's `docs/agents/cloud-setup.local.sh` if it has one |
| [`CLAUDE.md`](CLAUDE.md) | the cloud VM's known conditions, imported after [`RULES.md`](../RULES.md) |
| [`hooks/`](hooks/hooks.json) | session start (rules, `dockerd`, the target's own SessionStart hooks in multi-repo sessions, commit guards in the other clones), and save-work (unsaved work pushed to `claude/wip/*` when a turn ends on an API error, and every 20 minutes) |
| [`gcp/`](gcp/README.md) | a guard and a session-start status that keep an attached GCP project at $0.00 |
| [`githooks/`](githooks/pre-commit) | the pre-commit set in the other clones: a commit may not add the repo owner's login |
| [`skills/`](skills/) | `autopilot` (one unattended wake of a scheduled run), `autopilot-brief` (what a run of wakes did), `image-cache` (Docker layers shared through ghcr.io) |
