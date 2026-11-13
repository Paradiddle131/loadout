# Claude Code on the web

Conditions of the cloud VM that every session meets, whatever the repo; `cloud/setup.sh` imports this file after [`RULES.md`](../RULES.md) and [`FEEDBACK.md`](../FEEDBACK.md) into `~/.claude/CLAUDE.md`.
Work with them: they are not incidents to report or file issues about.

- Unattended run: follow the routine prompt and the target repo's `docs/agents/autopilot.md`, if it has one (the `autopilot` skill).
- A new condition goes here only after a real call confirms it, as one line; the evidence goes in the PR that adds it.

**Setup and session start**
- The environment's Setup field runs `cloud/setup.sh <target-repo>` from this collection's clone (the [README](README.md) has the guarded line); its result is a file snapshot reused for days, so the session-start hook re-runs the setup when the clone's copy differs from the one that made the snapshot (`~/.claude/cloud-setup.stamp`): a merged change reaches the next session with no edit of the field.
- Skills, hooks and rules load in place from the clone through this collection's plugins, so each session reads the fresh version.
- A scheduled task that starts a fresh session per firing gets no repositories, and an unguarded Setup field fails it before Claude starts (`Setup script failed`): keep the field guarded, and have the task's prompt `add_repo` and clone both repos, then run `cloud/setup.sh <target-repo>` itself.
- No `~/.claude/cloud-target` means the setup did not run (no plugins, no session-start hook, `dockerd` stopped): run `bash <clone>/cloud/setup.sh <target-repo>` once before other work; it also runs the session-start hook, the plugins load at the next session (read their `SKILL.md` files by path until then), and checking the Setup field goes to the owner in the handoff.
- Target repos carry no agent setup of their own: provisioning, rules, skills and guards live in this collection; a target's tools only it needs go in its `docs/agents/cloud-setup.local.sh`, which the setup runs.
- Commits in the other clones run `cloud/githooks/` (their `core.hooksPath`): `check-portable.sh` refuses an added owner login (derive `<owner>/<repo>` from `git remote get-url origin`, or link the tracker relatively, `../../issues`), and `check-process-ids.py` an added process id; `--all` audits a whole repo.
- Snapshots keep files, not processes: `dockerd`, Postgres and Compose stacks start fresh every session; the session-start hook starts `dockerd`.
- A session with several repos attached starts in `/home/user`, above the clones, and skips their hooks, settings and `.mcp.json`: `cd` into the target repo and read its `CLAUDE.md` / `AGENTS.md` yourself; the session-start hook runs the target's SessionStart hooks for you.
- `UV_NATIVE_TLS is deprecated` from uv means the session-start hook did not run (it swaps the variable for `UV_SYSTEM_CERTS`); it is harmless.
- Clones live at `/home/user/<repo>`, `$HOME` is `/root`; install extra CLIs user-local in `~/.local/bin`, pinned and checksum-verified.

**GitHub**
- REST only: `gh pr …` / `gh issue …` fail (GraphQL is 403); use `gh api` or the GitHub MCP tools.
- `gh api … -F body=@file.md` (capital `F`) reads the file; `-f` posts the literal path; read every body back.
- Draft → ready: GitHub MCP `update_pull_request` with `draft: false` (REST `draft=false` is silently ignored).
- `search/…` endpoints are refused: list `repos/<o>/<r>/issues?state=all` and filter with `--jq`.
- `gh api --paginate` follows `Link` headers to `repositories/<id>/…`, which the proxy refuses (403): page by hand with `&page=N`.
- `gh auth status` reports a failed login while `gh api` works (the proxy injects the token): trust `gh api /rate_limit`.
- REST `pulls/<n>/comments` can answer 403: read review threads with the MCP `pull_request_read`.
- An issue artifact is addressed by its `number` (`issues/<n>/artifacts/<number>`): `PATCH` with its `id` answers 404.
- Agent writes go out under the owner's account: GitHub notifies nobody, and a bot comment starts with `🤖` so it can be told from the owner's.
- Write only to repos of the owner's account: never file an issue, comment or PR on a repo outside it (an upstream bug goes into the owner's issue as a draft they may file).
- Only repos attached to the session are reachable; tag pushes and branch deletions are refused.
- GitHub Actions doesn't run on this account (no minutes): a red check is no signal; run the fast gates in the session and quote their results in the PR, and leave the long ones to the machine the repo's autopilot profile names for its `local` gates.

**Containers**
- Docker Hub rate-limits anonymous pulls (429): setup points `dockerd` at `mirror.gcr.io`.
- No local layer cache survives a session: share build layers and heavy images through ghcr.io (the `image-cache` skill).
- `docker build` steps that reach PyPI or npm fail TLS (containers don't trust the egress proxy's CA): build with `--network host`, the proxy build args, and `/root/.ccr/ca-bundle.crt` as an optional BuildKit secret the dependency step exports as `SSL_CERT_FILE` / `PIP_CERT`.
- ghcr.io: the proxy logs every request in as the owner (read and write packages), so plain `docker pull` / `push` work with no `docker login`; a `403 invalid token` means the environment's ghcr.io secret is malformed (owner's fix).
- kind runs on this cgroup v1 host without `CAP_SYS_RESOURCE` given kubelet `failCgroupV1: false` and containerd `restrict_oom_score_adj = true` (decide each from the host: Docker's cgroup version, and whether a privileged container may lower its OOM score); kind copies the host's loopback `HTTPS_PROXY` into its nodes, where it names the node itself: relay the kind gateway to the proxy from a host-network container, give each node's containerd that address (a systemd drop-in) and the proxy's CA, and pods can use the same relay.
- A kind lab with large images outgrows the disk allowance because Docker's image store, a local registry and every node keep their own copy: drop Docker's copy after pushing to the registry and pull layers back from a ghcr.io build cache.
- A restarted worker leaves a stale `/var/run/docker.pid` that stops `dockerd` from starting: remove it when its pid is gone.
- A cold VM can start `dockerd`'s managed containerd slower than `dockerd` waits (15 s) and `dockerd` exits; the session-start hook starts it a second time, so a `dockerd failed to start` notice means both attempts failed (see `/tmp/dockerd.log`).
- PostgreSQL 16 and Redis are installed but stopped (`service postgresql start`).

**Network**
- A blocked host answers `403` with `x-deny-reason: host_not_allowed`: the fix is the environment's Custom allowlist, which only the user can change; say so in the handoff.
- The egress proxy decodes `%2F` in URL paths: Cloud Storage's JSON API (`storage/v1/b/<bucket>/o/<a%2Fb>`, which `gcloud storage`, client libraries and OpenTofu's gcs backend use) answers 404 for an object whose name holds a slash, while listing works; keep such names slash-free, or read through the XML path (`storage.googleapis.com/<bucket>/<a/b>`).
- API keys may arrive as network secrets: the proxy adds the header for a named host, and the env var holds a placeholder; don't replace it.

**GCP projects** (`$GCP_PROJECT` set; the kit and its layers: `cloud/gcp/README.md`)
- An attached GCP project is a $0.00 lab unless the repo says otherwise: use only Always Free services, in the regions their free tier names; the session-start lines report the month-to-date cost, and any cost above zero stops GCP work for the session and goes first in the handoff.
- The credential comes from the proxy (`CLOUDSDK_AUTH_ACCESS_TOKEN=proxy-injected`; no key file); the `PreToolUse` guard refuses what moves a spend fence or creates a paid resource; treat a refusal as the answer and ask the owner, never route around it (client libraries, another tool, another API path).
- Check a permission with `testIamPermissions`, never by attempting the action: IAM changes take minutes to apply, and an attempt that succeeds has done the forbidden thing.
- Dry-run a query (`bq query --dry_run`, free) before running it, and keep `maximum_bytes_billed` on every job (`~/.bigqueryrc` carries the default); no streaming inserts (no free tier), load jobs or DML instead.

**Tools and turns**
- A foreground Bash call times out at 10 minutes: start long suites with `run_in_background` and wait for the completion notice; foreground `sleep` is blocked (use Monitor with an until-loop).
- A `run_in_background` job stops at its `timeout`, at most 2 hours, and the runner asks that one stopped at the longest limit not be restarted: split a longer job into resumable chunks under 2 hours, each started on its own.
- Start servers with `run_in_background`; a server started in a plain Bash call outlives the tool and keeps holding its port.
- Run subagents (reviewers included) in the foreground, or don't end the turn while one runs: the platform's stop hook sees uncommitted work and forces a commit before the review comes back.
- Timestamps you write come from `date -u +%FT%H:%MZ` at that moment; never estimate them.
- A usage limit (5-hour or weekly) can end a session mid-work, and nothing reads the plan's usage headlessly (only the interactive status line has it; never read credential files for it): persist as you go, pushing each branch and worktree after every commit, committing a long pass's log at each chunk, and never leaving results only in a subagent, a background job or the container.
  The save-work hook (`cloud/hooks/save-work.sh`) is the backstop: on a turn ended by an API error and every 20 minutes it pushes each clone's unsaved work to `claude/wip/<branch>-<session>`; a resuming session first lists `git ls-remote origin 'refs/heads/claude/wip/*'` and recovers what its branch lacks.
- The harness names a session branch and asks for a PR after each push; in an unattended wake the profile's branch rule and standing permission win.
- The stop hook forces a commit on a dirty tree: `git stash -u` before ending a turn that lands nothing.
- Scheduled wakes overlap and share external quotas (model free tiers, registries).
- A paid or quota-bound pass (model evals, load tests) first proves its setup on one known-easy case, unlogged, and stops after two misses; then read its first few logged results before leaving it running: an infrastructure failure the agent reports honestly (a refused connection, a withheld result) scores as a real answer and spends the whole budget.
- A pass that measures a new setup or switch first shows the change at work in its first few logged runs (the new tool called, the new step in the trace); if it does not, stop and ask the owner before the rest, whatever the pass costs: the runs would only repeat the setup it was copied from.
- OpenRouter: free models only (ids ending `:free`), in every repo and every run, evals included; a key's paid budget is never permission, and a spent free quota means wait for its reset or report the gap, never a paid model.
