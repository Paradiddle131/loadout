#!/bin/bash
# Every-session hook for cloud sessions, registered by the cloud plugin (cloud/hooks/hooks.json), which loads
# in place from the clone, so each session runs the fresh version.
# Stdout becomes session context: keep it to a few lines. Always exits 0.
set -u

# 1. The platform sets the deprecated UV_NATIVE_TLS, and uv warns on every call while it is
#    set. The env file is sourced before each Bash command, so unset it there and keep uv on
#    the system certificates (the proxy CA) under the new name.
if [ -n "${CLAUDE_ENV_FILE:-}" ] && [ -n "${UV_NATIVE_TLS:-}" ]; then
  printf 'unset UV_NATIVE_TLS\nexport UV_SYSTEM_CERTS=1\n' >> "$CLAUDE_ENV_FILE"
fi

# 1b. Shared content in this repo stays generic (its AGENTS.md): its pre-commit hook runs the checks
#     on what a session commits here.
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
git -C "$ROOT" config core.hooksPath .githooks 2>/dev/null || true

# 1c. The standing rules, rewritten from this clone in case the snapshot's file predates a move. Skills
#     need nothing here: the setup installed this clone's plugins, which load in place.
bash "$ROOT/cloud/memory.sh"
target=$(cat ~/.claude/cloud-target 2>/dev/null)

# 1e. The environment's setup ran from a snapshot that can be days old: when the clone's
#     cloud/setup.sh (or cloud/plugins.txt, or the target's own setup) differs from the one that made it,
#     run it again here, so a merged change reaches this session without editing the Setup field.
setup_stamp() { cat "$ROOT/cloud/setup.sh" "$ROOT/cloud/plugins.txt" ${target:+"$target/docs/agents/cloud-setup.local.sh"} 2>/dev/null | sha256sum | cut -d' ' -f1; }
if [ -n "$target" ] && [ "$(setup_stamp)" != "$(cat ~/.claude/cloud-setup.stamp 2>/dev/null)" ]; then
  if CLOUD_SETUP_REFRESH=1 timeout 200 bash "$ROOT/cloud/setup.sh" "$(basename "$target")" >/tmp/cloud-setup-refresh.log 2>&1; then
    echo "cloud: cloud/setup.sh changed since this environment's snapshot; re-ran it (/tmp/cloud-setup-refresh.log)"
  else
    echo "cloud: re-running the changed cloud/setup.sh failed; see /tmp/cloud-setup-refresh.log"
  fi
fi

# 1d. The other clones commit through cloud/githooks/ (a commit may not add the owner literally,
#     cloud/githooks/check-portable.sh), unless a repo has hooks of its own; .git/config is untracked, so the repo
#     carries nothing for it.
for g in "$(dirname "$ROOT")"/*/.git; do
  r=$(dirname "$g")
  [ "$r" = "$ROOT" ] && continue
  own=$(git -C "$r" config core.hooksPath)
  [ -z "$own" ] || [ "$own" = "$ROOT/cloud/githooks" ] || continue
  find "$g/hooks" -type f ! -name '*.sample' 2>/dev/null | grep -q . && continue
  git -C "$r" config core.hooksPath "$ROOT/cloud/githooks"
done

# 2. The VM ships Docker but doesn't start the daemon, and snapshots keep no processes.
if command -v dockerd >/dev/null && [ "$(id -u)" = 0 ] && ! docker info >/dev/null 2>&1; then
  # A restarted worker keeps the pid file of a daemon that is gone, and dockerd refuses to start over it.
  if [ -f /var/run/docker.pid ] && ! kill -0 "$(cat /var/run/docker.pid)" 2>/dev/null; then rm -f /var/run/docker.pid; fi
  # A cold VM can start dockerd's managed containerd slower than dockerd waits for it (15 s), and
  # dockerd exits; containerd keeps starting, so a second dockerd finds it up.
  for _ in 1 2; do
    setsid nohup dockerd >/tmp/dockerd.log 2>&1 < /dev/null &
    for _ in $(seq 30); do docker info >/dev/null 2>&1 && break 2; kill -0 $! 2>/dev/null || break; sleep 1; done
  done
  docker info >/dev/null 2>&1 && echo "cloud: dockerd started" ||
    echo "cloud: dockerd failed to start; see /tmp/dockerd.log"
fi

# 2b. A GCP project in the environment ($GCP_PROJECT) is a $0 lab: the byte cap, the guard's
#     registration, the credential's fences and the month-to-date cost, as a few lines of context.
[ -n "${GCP_PROJECT:-}" ] && timeout 120 bash "$ROOT/cloud/gcp/status.sh"

# 3. Multi-repo sessions start above the clones and skip the target's own hooks: run its
#    SessionStart commands here, as Claude Code would in a single-repo session.
if [ -n "$target" ] && [ -d "$target" ] && [ "${CLAUDE_PROJECT_DIR:-}" != "$target" ]; then
  echo "cloud: multi-repo session; target repo is $target: cd there and read its CLAUDE.md / AGENTS.md first."
  python3 - "$target/.claude/settings.json" <<'EOF' |
import json, sys
try:
    s = json.load(open(sys.argv[1]))
except (OSError, ValueError):
    sys.exit(0)
for m in s.get("hooks", {}).get("SessionStart", []):
    if (m.get("matcher") or "startup").find("startup") < 0:
        continue
    for h in m.get("hooks", []):
        if h.get("type") == "command":
            print(h["command"])
EOF
  while IFS= read -r cmd; do
    (cd "$target" && CLAUDE_PROJECT_DIR="$target" timeout 240 bash -c "$cmd") ||
      echo "cloud: target hook failed: $cmd"
  done
fi
exit 0
